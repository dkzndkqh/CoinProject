from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_internal_key
from app.forecast import service
from app.forecast.schemas import (
    ForecastCreate,
    ForecastSaveResponse,
    LatestBaseTimeResponse,
)

# market의 internal_router와 prefix가 같아도 된다. URL만 다르면 둘 다 /api/internal 아래에 붙는다.
# 키 검사는 라우터 전체에 걸어서 빼먹을 수 없게 한다.
router = APIRouter(
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_key)],
)


# body: ForecastCreate -> 요청 본문(JSON)을 이 클래스로 받고 검증.
@router.post(
    "/forecasts",
    response_model=ForecastSaveResponse,
    summary="Kronos 예측 결과 업로드 (같은 기준 시각이 이미 있으면 무시)",
)
def post_forecast(
    body: ForecastCreate,
    db: Annotated[Session, Depends(get_db)],
):
    saved = service.save_forecast(db, body)
    return ForecastSaveResponse(saved=saved)


@router.get(
    "/forecasts/latest-base-time",
    response_model=LatestBaseTimeResponse,
    summary="해당 코인, 모델이름의 마지막 예측 기준 시각 조회 (없으면 base_time이 null)",
)
def get_latest_base_time(
    # Literal[...]: 이 두 값 외에는 422로 막는다. 오타로 조용히 null이 오는 걸 방지한다.
    market: Annotated[Literal["KRW-BTC", "KRW-ETH"], Query()],
    # Query(min_length, max_length): ForecastCreate.model_name과 같은 길이 규칙
    model_name: Annotated[str, Query(min_length=1, max_length=50)],
    db: Annotated[Session, Depends(get_db)],
):
    base_time = service.get_latest_base_time(db, market, model_name)
    return LatestBaseTimeResponse(base_time=base_time)
