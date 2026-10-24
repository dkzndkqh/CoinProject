from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.clients import upbit
from app.market.models import Candle

# timeframe 이름 -> 업비트 분봉 단위(분). 1d는 분봉이 아니라 일봉 API를 따로 쓴다.
# 지원할 봉 종류를 추가하려면 여기에 한 줄만 넣으면 된다.

MINUTE_UNITS = {"1h": 60, "4h": 240}


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
