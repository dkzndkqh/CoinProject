from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

# 가격 하나의 규칙: 0보다 크고, NaN/무한대는 안 된다.
# (inf는 gt=0을 통과해 버려서 allow_inf_nan=False를 같이 건다. NaN은 비교가 항상 False라 gt=0에서 걸린다.)
# Annotated[타입, 규칙] 별칭을 만들어 두면 아래에서 여러 번 재사용할 수 있다.
Price = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class ForecastCreate(BaseModel):
    """내 PC(ai_inference)가 올리는 예측 결과 한 건의 요청 본문(JSON) 모양.
    자바의 요청 DTO(@RequestBody) + Bean Validation 어노테이션과 같은 역할이다.
    규칙에 어긋나면 FastAPI가 저장 로직에 오기 전에 422로 막는다.
    """

    market: Literal["KRW-BTC", "KRW-ETH"]

    # horizon: "4h", "1d", "7d" 같은 형식. 예측 기간은 설정값으로 바뀔 수 있어서
    # 값을 고정 목록으로 막지 않고 "숫자 + h 또는 d" 형식만 검사한다. (예: 30d를 나중에 추가해도 코드 수정 불필요)
    horizon: Annotated[str, Field(pattern=r"^[0-9]+(h|d)$", max_length=10)]

    # AwareDatetime: 시간대 정보가 있는 시각만 받는다 ("...Z" 또는 "+00:00" 포함).
    # 시간대 없는 시각이 오면 UTC인지 KST인지 알 수 없어서 422로 거절한다.
    base_time: AwareDatetime

    base_price: Price
    median: Price
    low_50: Price
    high_50: Price
    low_80: Price
    high_80: Price

    # 상승 확률은 0.0 ~ 1.0 (0 ~ 100%)
    up_probability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]

    model_name: Annotated[str, Field(min_length=1, max_length=50)]

    # model_validator(mode="after"): 필드를 하나씩 검사한 뒤, 값들끼리의 관계를 검사한다.
    # 자바에서 클래스 레벨 커스텀 검증(@ValidRange 같은 것)과 비슷하다.
    @model_validator(mode="after")
    def check_range_order(self):
        # 범위 순서: 80% 범위가 50% 범위를 감싸고, 중앙값은 50% 범위 안에 있어야 한다.
        # 샘플을 줄 세워 10/25/50/75/90번째 값을 뽑았다면 항상 이 순서가 맞는다. 어긋나면 계산 버그다.
        if not (
            self.low_80 <= self.low_50 <= self.median <= self.high_50 <= self.high_80
        ):
            raise ValueError(
                "low_80 <= low_50 <= median <= high_50 <= high_80 이어야 합니다"
            )
        return self


class ForecastSaveResponse(BaseModel):
    """저장 결과. saved=True면 새로 저장했고, False면 같은 예측이 이미 있어서 무시했다."""

    saved: bool


class LatestBaseTimeResponse(BaseModel):
    """마지막 기준 시각 조회 결과.
    base_time이 None이면 해당 코인·이름표의 예측이 아직 한 건도 없다는 뜻이다 (처음 실행).
    """

    base_time: AwareDatetime | None
