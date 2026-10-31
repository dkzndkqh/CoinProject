from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class KronosForecast(Base):
    """Kronos 예측 한 건 = 테이블 한 행.
    자바 JPA의 @Entity와 같은 역할이다.
    내 PC(ai_model)이 계산해서 /api/internal로 올린 결과를 저장한다.
    과거 예측도 지우지 않고 쌓는다 (8단계 평가에서 '그때 예측이 맞았나'를 비교하려고).
    """

    __tablename__ = "kronos_forecasts"

    # --- 기본 키: market + horizon + base_time + model_name 복합 키 ---
    # 같은 코인, 같은 예측 기간, 같은 기준 시각, 같은 모델(입력 이름표)의 예측은 한 행만 존재한다.
    # model_name이 키에 들어간 이유: 4h 입력과 1d 입력이 같은 시각에 같은 기간(예: 1d)을
    # 각각 예측하기 때문이다. model_name이 없으면 둘 중 하나가 중복으로 버려진다.

    # market: "KRW-BTC", "KRW-ETH" (candles와 같은 형식)
    market: Mapped[str] = mapped_column(String(20), primary_key=True)

    # horizon: 얼마 뒤를 예측했는지. "4h", "1d", "7d"
    # 기간 목록은 코드에 하드코딩하지 않고 설정값으로 관리하므로, DB는 문자열로만 받는다.
    horizon: Mapped[str] = mapped_column(String(10), primary_key=True)

    # base_time: 예측 기준 시각 (UTC). "이 시각까지의 캔들을 보고 예측했다"는 뜻.
    # 예측 대상 시각은 base_time + horizon으로 계산할 수 있어서 따로 저장하지 않는다.
    base_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

    # --- 예측 결과 ---
    # Kronos를 N번 돌려서 나온 미래 종가 N개를 가격 순으로 줄 세운 뒤,
    # 아래 값들을 ai_inference 코드가 계산해서 올린다 (Kronos가 직접 주는 값이 아니다).
    base_price: Mapped[float] = mapped_column(Float)

    # 예측 가격의 중앙값 (샘플링한 여러 예측 종가의 가운데 값)
    median: Mapped[float] = mapped_column(Float)

    # 50% 범위: "절반의 확률로 이 사이에 있다"의 아래쪽 끝(25% 지점)과 위쪽 끝(75% 지점).
    # 80% 범위보다 좁아서 "대체로 이 근처"라는 구체적인 감을 준다.
    low_50: Mapped[float] = mapped_column(Float)
    high_50: Mapped[float] = mapped_column(Float)

    # 80% 범위: "80% 확률로 이 사이에 있다"의 아래쪽 끝(10% 지점)과 위쪽 끝(90% 지점)
    low_80: Mapped[float] = mapped_column(Float)
    high_80: Mapped[float] = mapped_column(Float)

    # 상승 확률: 샘플 중 base_price보다 높게 나온 비율 (0.0 ~ 1.0)
    up_probability: Mapped[float] = mapped_column(Float)

    # --- 메타정보 ---
    # 어느 모델이 낸 예측인지 값 (예:NeoQuasar/Kronos-base|n300|4h42)
    model_name: Mapped[str] = mapped_column(String(50), primary_key=True)

    # 이 행을 저장한 시각. "업데이트 지연 " 표시를 위함
    # server_default=func.now() : 값을 안넣으면 DB가 현재 시각을 자동으로 채움
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
