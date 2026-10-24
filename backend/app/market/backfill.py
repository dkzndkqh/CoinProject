import time
import itertools

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.market import service
from app.market.models import Candle


# 백필 대상. 코인이나 봉 종류를 바꾸려면 여기만 고친다.
MARKETS = ["KRW-BTC", "KRW-ETH"]
TIMEFRAMES = ["1h", "4h", "1d"]

# 이 시각부터 현재까지 채운다 (2025-01-01 00:00 UTC).
START = datetime(2025, 1, 1, tzinfo=UTC)

# 한 번에 받을 개수. 업비트 최대값이 200이다.
PAGE_SIZE = 200

# 호출 사이에 쉬는 시간(초). 업비트는 초당 요청 수를 제한해서, 연달아 보내면 429 에러가 난다.
SLEEP_SECONDS = 0.2

# 봉 종류별 캔들 간격. 결측 검사에서 "다음 캔들이 이만큼 뒤에 있어야 정상"의 기준이다.
STEPS = {"1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}


def _candle_time(raw: dict) -> datetime:
    """업비트 응답에서 캔들 시작 시각을 UTC datetime으로 꺼낸다."""
    return datetime.fromisoformat(raw["candle_date_time_utc"]).replace(tzinfo=UTC)


def backfill(db: Session, market: str, timeframe: str, start: datetime = START) -> int:
    """한 코인의 한 봉 종류를, 최신에서 start까지 200개씩 거슬러 올라가며 저장한다.
    저장 요청한 캔들 수를 돌려준다.

    흐름: 최신 200개 받기 -> 저장 -> '받은 것 중 가장 오래된 시각'을 to로 삼아 그 이전 200개 받기 -> 반복.
    같은 캔들은 upsert라서 중간에 멈췄다가 다시 돌려도 중복이 생기지 않는다.
    # ponytail: 실패하면 처음부터 다시 돈다 (재개 기능 없음). 양이 적어서 몇십 초면 끝나므로 필요해질 때 추가한다.
    """

    saved = 0
    to = None  # None이면 가장 최신부터 받기

    while True:
        raw = service.fetch_candles(market, timeframe, PAGE_SIZE, to)
        if not raw:  # 더 받을 캔들이 없음
            break

        # 업비트는 최신 -> 과거 순서라서 마지막 항목이 가장 오래된 캔들이다.
        oldset = _candle_time(raw[-1])

        # start보다 오래된 캔들은 저장하지 않는다.
        wanted = [r for r in raw if _candle_time(r) >= start]
        saved += service.save_candles(db, timeframe, wanted)

        # 시작일에 닿았거나, 200개를 못 채웠다면(= 더 과거가 없다) 끝낸다.
        if oldset <= start or len(raw) < PAGE_SIZE:
            break
        to = oldset  # 다음 요청은 이 캔들 '이전'부터
        time.sleep(SLEEP_SECONDS)

    return saved


def find_gaps(
    db: Session, market: str, timeframe: str
) -> list[tuple[datetime, datetime]]:
    """저장된 캔들 사이에서 빠진 구간을 찾는다. (앞 캔들 시각, 뒤 캔들 시각) 쌍의 목록을 돌려준다.

    정상이면 이웃한 캔들의 간격이 봉 간격(1h면 1시간)과 같다.
    간격이 그보다 크면 그 사이 캔들이 빠진 것이다.
    업비트는 거래가 없던 시간대 캔들을 주지 않아서, 이 검사가 필요하다.
    """
    times = db.scalars(
        select(Candle.candle_time)
        .where(Candle.market == market, Candle.timeframe == timeframe)
        .order_by(Candle.candle_time)
    ).all()

    step = STEPS[timeframe]
    # zip(times, times[1:]): [t0,t1,t2]를 (t0,t1), (t1,t2) 쌍으로 만든다 = 이웃한 캔들끼리 비교.
    return [(a, b) for a, b in itertools.pairwise(times) if b - a > step]


def main() -> None:
    """모든 코인 x 봉 종류를 백필하고, 끝나면 결과와 결측을 출력한다."""
    db = SessionLocal()
    try:
        for market in MARKETS:
            for timeframe in TIMEFRAMES:
                saved = backfill(db, market, timeframe)
                gaps = find_gaps(db, market, timeframe)
                print(f"{market} {timeframe}: {saved}개 저장, 빠진 구간 {len(gaps)}곳")
                for before, after in gaps:
                    print(f" 빠진 구간 : {before} ~ {after}")
    finally:
        db.close()  # 에러가 나도 세션은 반드시 닫는다 (자바의 try-finally)


# 이 파일을 직접 실행했을 때만 main()을 부른다 (자바의 public static void main).
# 다른 파일이 import할 때는 실행되지 않는다.
if __name__ == "__main__":
    main()
