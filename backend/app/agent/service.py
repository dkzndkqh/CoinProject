import json
import logging
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.schemas import AnalysisResult
from app.clients import llm
from app.core.exceptions import AnalysisUnavailableError, NotFoundError
from app.forecast import service as forecast_service
from app.market import service as market_service

logger = logging.getLogger(__name__)

# 한국 시간.
# 시스템은 UTC로 저장하고, 에이전트가 사용자에게 말할 때만 KST로 보여준다.
KST = timezone(timedelta(hours=9))

# 에이전트에게 줄 예측 입력 종류
FORECAST_INPUTS = ("4h", "1d")

# 시스템 프롬프트 파일. 이 파일(service.py)이 있는 폴더 기준 prompts/system.md
# Path(__file__): 지금 파일의 경로, .parent: 그 폴더. 자바의 Paths.get(...).getParent()와 같다.
PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"

# Claude가 최종 답을 낼 때 채우는 양식 도구. input_schema는 AnalysisResult에서 자동으로 만든다.
SUBMIT_TOOL = {
    "name": "submit_analysis",
    "description": "시장 분석 결과를 제출한다. 사용자에게 보여줄 최종 답은 반드시 이 도구로 낸다.",
    "input_schema": AnalysisResult.model_json_schema(),
}

# 양식이 깨졌을 때 총 시도 횟수 (처음 1번 + 재요청 1번)
MAX_ATTEMPTS = 2

# 투자 권유가 아니라는 고지. 프롬프트에서는 Claude가 쓰지 않게 했고, 코드가 항상 붙인다.
DISCLAIMER = "이 내용은 데이터 기반 참고 분석이며 투자 권유가 아닙니다. 투자 판단과 결과의 책임은 본인에게 있습니다."

# 분석을 못 했을 때 사용자에게 보여줄 말
UNAVAILABLE_MESSAGE = "지금은 분석을 만들 수 없습니다. 잠시 후 다시 시도해 주세요."


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


def _load_system_prompt() -> str:
    """시스템 프롬프트 파일을 읽는다. 호출할 때마다 읽어서, 프롬프트를 고치면 서버 재시작 없이 바로 반영된다.
    encoding="utf-8"을 꼭 적는다. 자바의 Files.readString은 기본이 UTF-8이지만,
    파이썬은 Windows에서 기본이 CP949라서 한글이 깨질 수 있다.
    """
    return PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_message(question: str, data: dict) -> str:
    """Claude에게 보낼 사용자 메시지. 질문과 데이터를 태그로 나눠서, 질문 속 지시가 데이터와 섞이지 않게 한다.
    ensure_ascii=False: 한글을 \\uXXXX로 바꾸지 않고 그대로 둔다 (읽기 쉽고 토큰도 적다).
    """
    return (
        f"<question>\n{question}\n</question>\n\n"
        f"<data>\n{json.dumps(data, ensure_ascii=False)}\n</data>"
    )


def _available_horizons(data: dict) -> set[str]:
    """데이터에 실제로 있는 예측 기간 이름 모음. 예: {"4h", "8h", ..., "7d"}.
    예측이 아직 하나도 없으면 빈 집합이다 (그때는 기간을 검사하지 않는다).
    중괄호 {...for...}는 집합 컴프리헨션이다. 자바의 stream().flatMap(...).collect(toSet())과 같다.
    """
    return {
        horizon
        for forecast in data["forecasts"].values()
        if forecast is not None
        for horizon in forecast["horizons"]
    }


def _parse_result(raw: dict, available: set[str]) -> AnalysisResult | None:
    """Claude의 응답이 쓸 만한지 검사한다. 쓸 수 있으면 AnalysisResult, 아니면 이유를 로그에 남기고 None.
    검사 순서: 답이 잘렸나 -> 도구를 호출했나 -> 양식 규칙을 지켰나 -> 그 기간이 실제 예측에 있나
    """
    if raw["stop_reason"] == "max_tokens":
        # 답이 길이 제한에서 잘렸다. 도구 입력이 중간에 끊겼을 수 있어서 쓰지 않는다.
        logger.warning("에이전트 응답이 중간에 잘림 (max_tokens)")
        return None
    if raw["input"] is None:
        logger.warning(
            "에이전트가 양식도구를 호출하지 않음 (stop_reason=%s)", raw["stop_reason"]
        )
        return None
    try:
        result = AnalysisResult.model_validate(raw["input"])
    except ValidationError as e:
        logger.warning("에이전트 응답이 양식 규칙을 어김: %s", e)
        return None
    if available and result.horizon not in available:
        logger.warning(
            "에이전트가 데이터에 없는 기간을 고름: %s (있는 기간: %s)",
            result.horizon,
            sorted(available),
        )
        return None
    return result


def analyze(db: Session, market: str, question: str) -> dict:
    """질문에 대한 분석을 만들어 돌려준다.
    흐름: 데이터 조립 -> Claude 호출(양식 강제) -> 응답 검사 -> (깨졌으면 1번 재요청) -> 결과.
    market: "KRW-BTC" 또는 "KRW-ETH" (어느 코인인지는 호출하는 쪽이 정해서 넘긴다).
    에러: 데이터가 없으면 NotFoundError(404), 분석을 못 만들면 AnalysisUnavailableError(503).
    """
    data = build_agent_input(db, market)
    if data is None:
        raise NotFoundError("분석에 필요한 시장 데이터가 아직 준비되지 않았습니다")

    system = _load_system_prompt()
    user = _build_user_message(question, data)
    available = _available_horizons(data)

    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = llm.ask_with_tool(system, user, SUBMIT_TOOL)
        except llm.LLMError as e:
            # API 자체가 실패했다 (SDK가 이미 재시도했다). 또 불러도 소용없어서 바로 에러로 끝낸다.
            logger.error("Claude 호출 실패: %s", e)
            raise AnalysisUnavailableError(UNAVAILABLE_MESSAGE) from e

        logger.info(
            "에이전트 호출 market=%s attempt=%d stop_reason=%s tokens=%d/%d",
            market,
            attempt,
            raw["stop_reason"],
            raw["input_tokens"],
            raw["output_tokens"],
        )
        result = _parse_result(raw, available)
        if result is not None:
            break

    if result is None:
        logger.error(
            "에이전트 응답이 %d번 모두 쓸 수 없었음 (market=%s)", MAX_ATTEMPTS, market
        )
        raise AnalysisUnavailableError(UNAVAILABLE_MESSAGE)

    return {
        "market": market,
        "stance": result.stance,
        "horizon": result.horizon,
        "message": result.message,
        "price": data["price"],
        "price_time_kst": data["latest_candle_start_kst"],
        "disclaimer": DISCLAIMER,
    }
