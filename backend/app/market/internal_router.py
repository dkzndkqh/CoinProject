from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_internal_key
from app.market import service
from app.market.schemas import CandleResponse

# 내부 전용 라우터. 사용자용 /api/market 라우터와 파일을 나눈 이유는 인증이 다르기 때문이다.
# dependencies=[Depends(verify_internal_key)]: 이 라우터의 모든 URL에 키 검사를 한꺼번에 붙인다.
# 스프링에서 특정 URL 패턴(/api/internal/**)에 인터셉터를 거는 것과 같다.
# 앞으로 /api/internal 아래에 URL을 추가해도 키 검사를 빼먹을 일이 없다.

router = APIRouter(
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_key)],
)


# response_model=list[CandleResponse]: 응답을 CandleResponse 6개 필드로 걸러서 JSON으로 내보낸다.
# service가 돌려주는 Candle(DB 객체) 리스트가 여기서 자동으로 DTO로 바뀐다 (schemas의 from_attributes 덕분).
@router.get(
    "/candles",
    response_model=list[CandleResponse],
    summary="Kronos 입력용 마감 캔들 조회 (오래된 순)",
)
def get_candles(
    # Literal["KRW-BTC", "KRW-ETH"]: 이 두 값 중 하나만 허용한다. 다른 값이 오면 FastAPI가 422로 막는다.
    # (임의 문자열이 DB 조회로 흘러가지 않게 입구에서 막는 입력 검증이다. 자바의 enum 파라미터와 비슷하다.)
    market: Annotated[Literal["KRW-BTC", "KRW-ETH"], Query(description="마켓 코드")],
    timeframe: Annotated[Literal["1h", "4h", "1d"], Query(description="봉 종류")],
    db: Annotated[Session, Depends(get_db)],
    # ge=1, le=512: 1 이상 512 이하. Kronos 입력 한계(512)에 맞춘 상한이다.
    limit: Annotated[
        int, Query(ge=1, le=512, description="가장 최근 몇개의 캔들 정보를 줄지")
    ] = 400,
    start_time: Annotated[
        datetime | None, Query(description="이 시각 이후 캔들만 (UTC, 선택)")
    ] = None,
    end_time: Annotated[
        datetime | None, Query(description=" 이 시각 이전 캔들만 (UTC, 선택)")
    ] = None,
):
    """마감된 캔들만, 오래된 순서로 돌려준다. 조건에 맞는 캔들이 없으면 빈 리스트([])다."""
    return service.get_closed_candles(
        db, market, timeframe, limit, start_time, end_time
    )
