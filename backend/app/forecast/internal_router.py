from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_internal_key
from app.forecast import service
from app.forecast.schemas import ForecastCreate, ForecastSaveResponse

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
