from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.forecast import service as forecast_service
from app.market import service as market_service

# 한국 시간.
# 시스템은 UTC로 저장하고, 에이전트가 사용자에게 말할 때만 KST로 보여준다.
KST = timezone(timedelta(hours=9))

# 에이전트에게 줄 예측 입력 종류
FORECAST_INPUTS = ("4h", "1d")


def _kst_text(dt: datetime) -> str:
    """시각을 한국 시간 문자열로 바꾼다. 예: "2026-10-31 17:00 KST"."""
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def _pct_vs(value: float, price: float) -> float:
    """value가 price보다 몇 % 높은지(+) 낮은지(-)를 계산한다."""
    return round((value - price) / price * 100, 2)


def _horizon_delta(horizon: str) -> timedelta:
    """예측 기간 문자열을 시간 길이로 변경 "12h -> 12시간,"""
    number, unit = int(horizon[:-1]), horizon[-1]
    return timedelta(days=number) if unit == "d" else timedelta(hours=number)


def _shape_forecast(fc: dict, price: float, now: datetime) -> dict:
    """forecast 서비스가 준 원본 예측을 에이전트에게 줄 모양으로 바꾼다.
    price: 현재가. 예측 가격이 현재가보다 몇 % 위·아래인지 계산하는 기준이다.
    주의: up_probability는 현재가가 아니라 예측을 시작한 가격(base_price)보다 높게 끝날 확률이다.
    """
    horizons = {}
    for h in fc["horizons"]:
        # 이 칸의 목표 시각 = 예측 기준 시각 + 기간. "지금부터 몇 시간 뒤"는 now와의 차이다.
        # 예측이 오래됐으면 음수가 될 수 있다 (이미 지나간 시점)
        target = fc["base_time"] + _horizon_delta(h["horizon"])
        up = round(h["up_probability"], 2)
        horizons[h["horizon"]] = {
            "target_time_kst": _kst_text(target),
            "hours_from_now": round((target - now).total_seconds() / 3600, 1),
            "median": h["median"],
            "median_vs_price_pct": _pct_vs(h["median"], price),
            "range_80": [h["low_80"], h["high_80"]],
            "range_80_vs_price_pct": [
                _pct_vs(h["low_80"], price),
                _pct_vs(h["high_80"], price),
            ],
            "up_probability": up,
            "down_probability": round(
                1 - up, 2
            ),  # 합이 1이 되도록 반올림한 값에서 뺀다
        }
    return {
        "base_time_kst": _kst_text(fc["base_time"]),
        # 이 예측이 몇 시간 전 것인지. 1d 입력 예측은 최대 24시간 전일 수 있다.
        "hours_ago": round((now - fc["base_time"]).total_seconds() / 3600, 1),
        "base_price": fc["base_price"],  # 예측을 시작한 가격
        "horizons": horizons,
    }


def build_agent_input(db: Session, market: str) -> dict | None:
    """에이전트에게 항상 넣어 줄 데이터를 한 묶음으로 모은다. 캔들이 모자라 지표를 못 만들면 None.
    구성: 현재가·최근 수익률 + 지표 판정(4h, 1d) + Kronos 예측(4h 입력, 1d 입력).
    숫자 계산은 모두 코드가 하고, 결론(방향, 일치 여부 등)은 만들지 않는다. 해석은 LLM의 몫이다.
    """
    judgement = market_service.get_indicator_judgement(db, market)
    if judgement is None:
        return None

    price = judgement["4h"]["price"]  # 현재가 (최신 캔들 종가)
    now = datetime.now(UTC)

    forecasts = {}
    for tag in FORECAST_INPUTS:
        fc = forecast_service.get_latest_forecast(db, market, tag)
        # 예측이 아직 없는 입력은 None
        forecasts[tag] = _shape_forecast(fc, price, now) if fc else None

    return {
        "market": market,
        "now_kst": _kst_text(now),
        "price": price,
        # 현재가는 이 캔들의 현재까지 종가다 (최대 15분 지연). 캔들 시작 시각이지 가격 시각이 아니다.
        "latest_candle_start_kst": _kst_text(
            datetime.fromisoformat(judgement["4h"]["price_time"])
        ),
        "recent_returns_pct": market_service.get_recent_returns(db, market, price),
        "indicators": {"4h": judgement["4h"], "1d": judgement["1d"]},
        "forecasts": forecasts,
    }
