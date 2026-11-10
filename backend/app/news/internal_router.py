from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_internal_key
from app.news import service
from app.news.schemas import SentimentBatch, SentimentSaveResponse, UnscoredArticle

router = APIRouter(
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_key)],
)


@router.get(
    "/news/unscored",
    response_model=list[UnscoredArticle],
    summary="뉴스 분석을 하지 않은 기사 조회(최신순)",
)
def get_unscored_news(
    # 주의: 파이썬은 기본값이 있는 매개변수 뒤에 기본값 없는 매개변수를 둘 수 없다.
    # 그래서 기본값이 없는 db를 앞에, 기본값(100)이 있는 limit를 뒤에 둔다.
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    return service.get_unscored(db, limit)


@router.post(
    "/news/sentiment",
    response_model=SentimentSaveResponse,
    summary="기사별 감성 분석 업로드 (이미 점수가 있으면 무시)",
)
def post_news_sentiment(
    body: SentimentBatch,
    db: Annotated[Session, Depends(get_db)],
):
    return SentimentSaveResponse(updated=service.save_sentiments(db, body.results))
