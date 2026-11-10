from typing import Annotated, Literal

from pydantic import BaseModel, Field


class UnscoredArticle(BaseModel):
    """감성 점수가 아직 없는 기사. ai_inference가 FinBERT에 넣을 글(제목+요약)과 id를 받아 간다."""

    id: int
    title: str
    summary: str | None  # 요약이 없는 기사도 있어서 None 허용


class SentimentItem(BaseModel):
    """기사 한 건의 감성 결과. 자바의 요청 DTO + Bean Validation과 같은 역할이다."""

    id: int

    # Literal: 이 세 값 외에는 422로
    label: Literal["positive", "negative", "neutral"]

    # score: 긍정 확률 - 부정 확률. -1(아주 부정) ~ +1(아주 긍정)
    # allow_inf_nan=False: 무한대는 범위 검사를 통과해 버릴 수 있어서 같이 막는다.
    score: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]

    # 어느 모델이 계산했는지
    model_name: Annotated[str, Field(min_length=1, max_length=50)]


class SentimentBatch(BaseModel):
    """한 번에 여러 기사의 결과를 올리는 요청 본문. 1건 이상 200건 이하."""

    results: Annotated[list[SentimentItem], Field(min_length=1, max_length=200)]


class SentimentSaveResponse(BaseModel):
    """실제로 저장된 건수. 이미 점수가 있던 기사는 세지 않는다."""

    updated: int
