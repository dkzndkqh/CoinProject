import logging
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.clients import alternative, binance, upbit
from app.market import indicators
from app.market.models import Candle, MarketSnapshot

logger = logging.getLogger(__name__)

# timeframe 이름 -> 업비트 분봉 단위(분). 1d는 분봉이 아니라 일봉 API를 따로 쓴다.
# 지원할 봉 종류를 추가하려면 여기에 한 줄만 넣으면 된다.

MINUTE_UNITS = {"1h": 60, "4h": 240}

INDICATOR_TIMEFRAMES = ("4h", "1d")  # 지표 판정 봉

# 우리 마켓 코드 -> 바이낸스 선물 심볼. 외부 API 형식은 service가 우리 용어로 번역한다.
BINANCE_SYMBOLS = {"KRW-BTC": "BTCUSDT", "KRW-ETH": "ETHUSDT"}


def fetch_candles(
    market: str, timeframe: str, count: int, to: datetime | None = None
) -> list[dict]:
    """timeframe("1h", "4h", "1d")에 맞는 업비트 API를 골라서 캔들을 가져온다.
    백필과 15분 수집이 둘 다 이 함수를 쓴다.
    지원하지 않는 timeframe이면 KeyError가 난다 (잘못된 값을 조용히 넘기지 않기 위해 일부러 그대로 둔다).
    """
    if timeframe == "1d":
        return upbit.get_daily_candles(market, count, to)
    return upbit.get_minute_candles(market, MINUTE_UNITS[timeframe], count, to)


def _to_row(timeframe: str, raw: dict) -> dict:
    """업비트 응답 dict 한 개를 우리 candles 테이블의 컬럼 이름으로 바꾼다.
    업비트 필드 이름(opening_price 등)이 우리 컬럼 이름(open 등)과 달라서 필요한 변환이다.
    """
    return {
        "market": raw["market"],
        "timeframe": timeframe,
        # 업비트는 "2025-01-01T00:00:00" 처럼 시간대 표시가 없는 UTC 문자열을 준다.
        # fromisoformat으로 datetime으로 바꾸고, replace(tzinfo=UTC)로 'UTC'라는 표시를 붙인다.
        # (값을 바꾸는 게 아니라 이 시각이 UTC라고 꼬리표를 다는 것이다.)
        "candle_time": datetime.fromisoformat(raw["candle_date_time_utc"]).replace(
            tzinfo=UTC
        ),
        "open": raw["opening_price"],
        "high": raw["high_price"],
        "low": raw["low_price"],
        # 업비트에서 종가(진행 중이면 현재가)는 trade_price
        "close": raw["trade_price"],
        "volume": raw["candle_acc_trade_volume"],
    }


def save_candles(db: Session, timeframe: str, raw_candles: list[dict]) -> int:
    """업비트에서 받은 캔들들을 DB에 저장한다 (upsert). 저장한 행 수를 돌려준다.

    upsert = 없으면 insert, 이미 있으면 update.
    '있는지'는 기본 키(market, timeframe, candle_time)로 판단한다.
    아직 진행 중인 캔들은 15분마다 값(close, high 등)이 바뀌므로 덮어써야 하기 때문에 필요하다.
    PostgreSQL의 INSERT ... ON CONFLICT DO UPDATE 한 번으로 처리해서,
    '조회 후 insert/update 분기'보다 빠르고 동시에 실행돼도 안전하다.
    """
    if not raw_candles:
        return 0
    rows = [_to_row(timeframe, raw) for raw in raw_candles]

    # sqlalchemy.dialects.postgresql.insert: PostgreSQL 전용 insert.
    # 일반 insert에는 없는 on_conflict_do_update를 쓰기 위해 이걸 가져왔다.
    stmt = insert(Candle).values(rows)

    # stmt.excluded: "INSERT하려고 했던 새 값"을 가리킨다.
    # 충돌(이미 같은 키가 있음)이 나면 기존 행을 새 값으로 덮어쓴다.
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            "market",
            "timeframe",
            "candle_time",
        ],  # 충돌 판단 기준 = 기본 키
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            # 덮어쓸 때는 '수집 시각'도 지금으로 갱신한다 (현재가의 기준 시각이 된다).
            "fetched_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()  # 여기서 확정(커밋)한다. 실패하면 예외가 나고 아무것도 저장되지 않는다.
    return len(rows)


def get_indicator_judgement(db: Session, market: str) -> dict | None:
    """코인 하나의 4h/1d 지표 판정을 돌려준다. 에이전트(3단계)도 이 함수를 그대로 쓴다.
    흐름: DB 캔들 로드(결측 보정) -> 지표 계산 -> 판정 dict.
    반환: {"market": "KRW-BTC", "4h": {...}, "1d": {...}}
        캔들이 모자란 market이면 None (router가 404로 바꾼다).
    `dict | None`은 "dict 또는 None"이라는 타입 표기다 (자바의 Optional<Map>과 비슷).
    """
    result = {"market": market}
    for timeframe in INDICATOR_TIMEFRAMES:
        df = indicators.load_candles_df(db, market, timeframe)
        # judge_indicators는 최소 3개 행(iloc[-3])이 필요하다. 그보다 적으면 판정할 수 없다.
        if len(df) < 3:
            return None
        result[timeframe] = indicators.judge_indicators(indicators.add_indicators(df))
    return result


def floor_time(dt: datetime, minutes: int) -> datetime:
    """시각을 minutes 단위로 내린다. 15분이면 12:07 -> 12:00, 12:29 -> 12:15.
    스냅샷의 snapshot_time을 일정한 칸에 맞추려는 것이다 (재수집하면 같은 칸을 덮어쓴다).
    minutes는 60의 약수(5, 10, 15, 30)일 때만 맞다.
    """
    return dt.replace(minute=dt.minute - dt.minute % minutes, second=0, microsecond=0)


def _safe(label: str, fetch):
    """외부 API 호출 하나를 안전하게 감싼다. 실패하면 로그를 남기고 None을 돌려준다.
    fetch는 '인자 없이 호출하는 함수'다 (자바의 Supplier<T>, 람다 () -> ... 와 같다).
    소스 하나가 실패해도 다른 소스와 캔들 수집이 멈추지 않게 하려는 것이다.
    """

    try:
        return fetch()
    except Exception:
        logger.exception("스냅샷 수집 실패: %s", label)
        return None


def fetch_snapshot_rows(markets: list[str], snapshot_time: datetime) -> list[dict]:
    """코인마다 스냅샷 한 행(dict)을 만든다. 실패한 값은 None(DB에서 NULL)으로 둔다.
    바이낸스의 숫자는 문자열("97714.439")로 오기 때문에 float, int로 바꾼다.
    변환(parse)도 _safe 안에서 하므로, 응답 모양이 바뀌어도 이 값만 None이 되고 나머지는 저장된다.
    """
    # 공포, 탐욕은 공통 값이라 한번만 받아서 모든행에 넣기
    fear_greed = _safe("fear_greed", lambda: int(alternative.get_fear_greed()["value"]))

    rows = []
    for market in markets:
        symbol = BINANCE_SYMBOLS[market]
        rows.append(
            {
                "market": market,
                "snapshot_time": snapshot_time,
                "open_interest": _safe(
                    f"open_interest {symbol}",
                    lambda symbol=symbol: float(
                        binance.get_open_interest(symbol)["openInterest"]
                    ),
                ),
                "long_short_ratio": _safe(
                    f"long_short_ratio {symbol}",
                    lambda symbol=symbol: float(
                        binance.get_long_short_ratio(symbol)["longShortRatio"]
                    ),
                ),
                "fear_greed": fear_greed,
            }
        )
    return rows


def save_snapshots(db: Session, rows: list[dict]) -> int:
    """스냅샷들을 DB에 저장한다 (upsert). 저장한 행 수를 돌려준다.
    같은 (market, snapshot_time)이 있으면 덮어쓴다. save_candles와 같은 방식이다.
    """
    if not rows:
        return 0
    stmt = insert(MarketSnapshot).values(rows)

    # coalesce(새 값, 기존 값): 새 값이 NULL이면 기존 값을 그대로 둔다.
    # 같은 칸을 다시 수집했는데 이번에는 한 소스가 실패해서 NULL이 온 경우,
    # 먼저 저장된 정상 값을 NULL로 덮어써서 지우는 일을 막으려는 것이다.

    stmt = stmt.on_conflict_do_update(
        index_elements=["market", "snapshot_time"],
        set_={
            "open_interest": func.coalesce(
                stmt.excluded.open_interest, MarketSnapshot.open_interest
            ),
            "long_short_ratio": func.coalesce(
                stmt.excluded.long_short_ratio, MarketSnapshot.long_short_ratio
            ),
            "fear_greed": func.coalesce(
                stmt.excluded.fear_greed, MarketSnapshot.fear_greed
            ),
            "fetched_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)
