import logging
import time
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.market import service
from app.market.backfill import MARKETS, SLEEP_SECONDS, TIMEFRAMES, backfill, find_gaps

logger = logging.getLogger(__name__)

COLLECT_INTERVAL_MINUTES = 15  # 수집 주기
COLLECT_COUNT = 5  # 매번 받을 최신 캔들 수
RECOVER_DAYS = 3  # 서버 시작 시 몇일 전부터 다시 받아 구멍을 메울지
GAP_CHECK_TIMEFRAMES = ["4h", "1d"]  # 결측을 감시할 봉
GAP_CHECK_DAYS = 7  # 최근 며칠 안의 결측만 경고


def collect_latest() -> None:
    """15분마다 호출된다. 모든 코인 x 봉 종류의 최신 캔들을 받아 저장한다.
    스케줄러가 별도 스레드에서 부르기 때문에, FastAPI의 Depends(get_db) 대신 세션을 직접 열고 닫는다.
    """
    db = SessionLocal()
    try:
        for market in MARKETS:
            for timeframe in TIMEFRAMES:
                try:
                    raw = service.fetch_candles(market, timeframe, COLLECT_COUNT)
                    service.save_candles(db, timeframe, raw)
                except Exception:
                    # 한 건이 실패해도 나머지는 계속한다. 다음 주기(15분 뒤)에 다시 받는다.
                    # logger.exception은 에러 메시지와 함께 스택 트레이스도 남긴다.
                    logger.exception("수집 실패: %s %s", market, timeframe)
                    db.rollback()  # 실패한 트랜잭션이 남아 다음 저장을 막지 않도록 되돌린다.
                time.sleep(SLEEP_SECONDS)
        _warn_recent_gaps(db)
        logger.info("수집 완료")
    finally:
        db.close()


def _warn_recent_gaps(db) -> None:
    """4h·1d에 최근 결측이 있으면 경고 로그를 남긴다 (결측 대비 1단계: 발견)."""
    cutoff = datetime.now(UTC) - timedelta(days=GAP_CHECK_DAYS)
    for market in MARKETS:
        for timeframe in GAP_CHECK_TIMEFRAMES:
            for before, after in find_gaps(db, market, timeframe):
                if after >= cutoff:
                    logger.warning(
                        "결측 캔들 : %s %s %s ~ %s", market, timeframe, before, after
                    )


def recover_recent() -> None:
    """서버가 켜질 때 한 번 호출된다. 꺼져 있던 동안 놓친 최근 캔들을 다시 받아 메운다
    (결측 대비 2단계: 복구). upsert라서 이미 있는 캔들과 겹쳐도 중복이 생기지 않는다.
    """
    # 며칠 전 '자정(UTC)'부터 받는다. 자정에 맞춰야 일봉과 4시간봉의 시작 경계가 잘리지 않는다.
    start = (datetime.now(UTC) - timedelta(days=RECOVER_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    db = SessionLocal()

    try:
        for market in MARKETS:
            for timeframe in TIMEFRAMES:
                try:
                    backfill(db, market, timeframe, start)
                except Exception:
                    logger.exception("복구 실패: %s %s", market, timeframe)
                    db.rollback()
                time.sleep(SLEEP_SECONDS)
        logger.info("복구 완료 (%s부터)", start)
    finally:
        db.close()


def collect_snapshots() -> None:
    """15분마다 호출된다. 코인별 시장 지표(미결제약정, 롱숏 비율, 공포·탐욕)를 받아 저장한다.
    캔들 수집(collect_latest)과 별도 작업으로 돌려서, 한쪽이 느려지거나 실패해도 서로 영향이 없다.
    """
    db = SessionLocal()
    try:
        # 지금 시각을 수집 주기(15분) 칸에 맞춰 내린다. 12:07 -> 12:00
        snapshot_time = service.floor_time(datetime.now(UTC), COLLECT_INTERVAL_MINUTES)
        rows = service.fetch_snapshot_rows(MARKETS, snapshot_time)
        service.save_snapshots(db, rows)
        logger.info("바이낸스 데이터 스냅샷 수집 완료 (%s)", snapshot_time)
    except Exception:
        # 저장 단계의 예외 (DB 오류 등). 다음 주기에 다시 시도한다.
        logger.exception("바이낸스 데이터 스냅샷 저장 실패")
        db.rollback()
    finally:
        db.close()
