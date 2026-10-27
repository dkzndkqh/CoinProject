import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.error_handlers import register_exception_handlers
from app.core.scheduler import scheduler
from app.market.collector import (
    COLLECT_INTERVAL_MINUTES,
    collect_latest,
    collect_snapshots,
    recover_recent,
)
from app.market.router import router as market_router

# 앱 전체 로그 설정. 이게 없으면 남기는 logger.info가 화면에 안 보인다.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작과 종료 때 실행할 일. yield 앞이 시작, 뒤가 종료다.
    스프링의 @PostConstruct / @PreDestroy를 한 곳에 모은 것과 같다.
    """
    recover_recent()  # 시작할 때 놓친 캔들 먼저 저장
    scheduler.add_job(
        collect_latest, "interval", minutes=COLLECT_INTERVAL_MINUTES
    )  # 15분마다 반복
    scheduler.add_job(
        collect_snapshots, "interval", minutes=COLLECT_INTERVAL_MINUTES
    )  # 시장 지표 스냅샷도 15분마다
    scheduler.start()
    yield  # 여기서부터 서버가 요청을 받는다.
    scheduler.shutdown()  # 종료할 때 스케줄러도 멈춘다.


app = FastAPI(
    lifespan=lifespan,
    title="Coin Agent API",
    description="BTC, ETH 분석 및 가격예측 AI 에이전트",
)
app.include_router(market_router)
register_exception_handlers(app)  # 에러 -> 공통 JSON 응답 변환기를 앱에 등록
