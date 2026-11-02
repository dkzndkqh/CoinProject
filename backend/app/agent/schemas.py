from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    """에이전트(Claude)가 `submit_analysis` 도구로 채워서 돌려주는 분석 결과의 양식.
    자바의 응답 DTO + Bean Validation(@Valid)과 같은 역할이다.
    Claude가 준 값이 이 규칙에 어긋나면 ValidationError가 나고, 서비스가 그 에러를 처리한다.

    같은 클래스에서 두 가지를 얻는다.
    1) 값 검증: AnalysisResult.model_validate(dict) -> 규칙에 맞으면 객체, 아니면 에러
    2) Claude에게 줄 양식 설명: AnalysisResult.model_json_schema() -> JSON 스키마 dict
    그래서 도구 정의를 따로 손으로 쓰지 않아도 되고, 양식이 바뀔 때 한 곳만 고치면 된다.
    """

    # Literal["매수", "매도", "관망"]: 이 세 문자열 중 하나만 허용한다 (자바의 enum 3개짜리와 같다).
    # Field(description=...)는 JSON 스키마에 설명으로 들어가서 Claude가 칸의 뜻을 읽는다.
    # (자바 Swagger의 @Schema(description = "...")와 비슷하지만, 여기서는 Claude가 읽는다는 점이 다르다)
    stance: Literal["매수", "매도", "관망"] = Field(
        description="매매 방향. 매수, 매도, 관망 중 하나"
    )

    # horizon: "4h", "1d", "7d" 같은 형식. 예측 기간은 설정값으로 바뀔 수 있어서
    # 고정 목록으로 막지 않고 "숫자 + h 또는 d" 형식만 검사한다. (forecast/schemas.py와 같은 방식)
    # 이 기간이 실제 예측 데이터에 있는지는 서비스에서 따로 확인한다.
    horizon: Annotated[str, Field(pattern=r"^[0-9]+(h|d)$", max_length=10)] = Field(
        description="이 의견이 가리키는 예측 기간. 예: 4h, 1d, 3d, 7d."
    )

    # message: 사용자가 읽는 설명 글. 비어 있으면 안 된다.
    # 상한은 넉넉하게(프롬프트에서 15줄 이내로 요청하지만 글자 수로 정확히 막기는 어렵다).
    # 이 상한은 Claude가 폭주해서 너무 긴 글을 보내는 것만 막는 안전장치다.
    message: Annotated[str, Field(min_length=10, max_length=3000)] = Field(
        description="사용자에게 보여줄 한국어 설명 글"
    )
