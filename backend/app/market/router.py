from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.market import service

# APIRouter: URL 묶음. 스프링 컨트롤러 클래스에 붙이는 @RequestMapping("/api/market")과 같다.
# main.py에서 app.include_router()로 앱에 붙인다.
router = APIRouter(prefix="/api/market", tags=["market"])

# 사용자가 URL에 쓰는 이름 -> 업비트 마켓 코드. 이 둘만 허용한다.
# (임의 문자열이 DB 조회로 흘러가지 않게 입구에서 막는 입력 검증이다.)
MARKETS = {"btc": "KRW-BTC", "eth": "KRW-ETH"}


# @router.get: 스프링의 @GetMapping과 같다. {coin}은 @PathVariable에 해당한다.
# 함수 인자 이름이 URL의 {coin}과 같으면 FastAPI가 자동으로 넣어준다.
# db: Session = Depends(get_db) -> 요청마다 DB 세션을 주입받는다 (@Autowired와 비슷, 끝나면 자동 close).
@router.get(
    "/{coin}/indicators",
    summary="코인별 4h/1d 지표 판정 조회",
    responses={
        404: {"description": "지원하지 않는 코인이거나 캔들 데이터가 아직 없음"}
    },
)
def get_indicators(
    coin: Annotated[
        str,
        Path(description="코인 이름 (btc 또는 eth, 대소문자 무관)", examples=["btc"]),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    """GET /api/market/btc/indicators -> 4h/1d 지표 판정(JSON)."""
    market = MARKETS.get(coin.lower())  # dict.get: 없으면 예외 대신 None을 돌려준다

    if market is None:
        # HTTPException: 스프링의 ResponseStatusException과 같다. 404 = 없는 코인.
        raise HTTPException(
            status_code=404, detail="지원하지 않는 코인입니다 (btc, eth)"
        )

    result = service.get_indicator_judgement(db, market)

    if result is None:
        raise HTTPException(status_code=404, detail="캔들 데이터가 아직 없습니다")
    return result  # dict를 돌려주면 FastAPI가 JSON으로 바꿔 응답한다
