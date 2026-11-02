from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent import service
from app.agent.schemas import AnalyzeRequest, AnalyzeResponse
from app.core.db import get_db

# 스프링 컨트롤러의 @RequestMapping("/api/agent")와 같다. main.py에서 앱에 붙인다.
router = APIRouter(prefix="/api/agent", tags=["agent"])


# response_model: 응답이 이 양식을 지키는지 내보내기 직전에 검사하고, Swagger 문서에도 이 모양이 나온다.
# responses: Swagger에 에러 응답을 설명하는 용도다 (동작에는 영향 없음).
@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="질문에 대한 코인 분석 (매수,매도,관망 + 예상범위)",
    responses={
        404: {"description": "분석에 필요한 시장 데이터가 아직 없음"},
        503: {
            "description": "분석을 만들 수 없음 (Claude 호출 실패 또는 응답 형식 오류)"
        },
    },
)
def analyze(
    # body : 요청 본문(JSON)을 AnalyzeRequest로 바꿔 준다.
    body: AnalyzeRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """POST /api/agent/analyze  {"market": "KRW-BTC", "question": "3일 뒤 어때?"}
    여기서는 연결만 한다. 데이터 조립, Claude 호출, 검사는 모두 service.analyze()가 한다.
    에러(404, 503)는 서비스가 AppError를 던지면 전역 핸들러가 {"error": {...}} 모양으로 바꿔 준다.
    """
    return service.analyze(db, body.market, body.question)
