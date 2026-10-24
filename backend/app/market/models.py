from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Candle(Base):
    """캔들(봉) 한 개 = 테이블 한 행.
    자바 JPA의 @Entity 클래스와 같은 역할이다.
    Base를 상속하면 Alembic이 이 클래스를 보고 테이블 생성 스크립트를 만들 수 있다.
    """

    # 실제 DB 테이블 이름 
    __tablename__ = "candles"

    # --- 기본 키: market + timeframe + candle_time 세 컬럼을 묶은 복합 키 ---
    # 같은 코인, 같은 봉 종류, 같은 시작 시각의 캔들은 한 행만 존재할 수 있다.
    # 그래서 같은 캔들을 두 번 저장하려 하면 DB가 막아주고, upsert의 기준이 된다.
    # primary_key=True를 여러 컬럼에 붙이면 복합 키가 된다
    # (JPA에서는 @IdClass나 @EmbeddedId가 필요한 부분인데 SQLAlchemy는 훨씬 간단하다).

    # market: "KRW-BTC", "KRW-ETH" 같은 업비트 마켓 코드
    market: Mapped[str] = mapped_column(String(20), primary_key=True)

    # timeframe: "1h", "4h", "1d" 중 하나 (봉 종류)
    timeframe : Mapped[str] = mapped_column(String(10), primary_key=True)

    # candle_time: 이 캔들이 시작되는 시각 (UTC 기준).
    # timezone=True: 시간대 정보를 같이 저장한다. 시간대 없는 시각은 KST/UTC가 섞여 버그가 나기 쉽다.
    candle_time : Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    # --- 가격과 거래량 ---
    # Float: 소수를 쓰는 자료형 (자바의 double). 돈 계산용 BigDecimal이 아니라 분석용이다.
    # pandas가 지표를 계산할 때 float이 바로 쓰이고, Decimal이면 변환이 번거롭다.

    # 시가: 캔들이 시작할 때의 가격
    open: Mapped[float] = mapped_column(Float) 
    # 고가: 캔들 동안 가장 높았던 가격
    high: Mapped[float] = mapped_column(Float)
    # 저가: 캔들 동안 가장 낮았던 가격
    low: Mapped[float] = mapped_column(Float)
    # 종가: 캔들이 끝날 때의 가격 (진행 중이면 현재가)
    close: Mapped[float] = mapped_column(Float)
    # 거래량 (코인 개수 기준)
    volume: Mapped[float] = mapped_column(Float)

    # --- 수집 시각 ---
    # 이 행을 업비트에서 마지막으로 받아 저장한 시각.
    # 진행 중인 캔들의 close는 "현재가"인데, 그 값이 몇 시 기준인지 알려주는 역할이다.
    # server_default=func.now(): 값을 안 넣으면 DB가 현재 시각을 자동으로 채운다.
    # upsert로 덮어쓸 때는 저장 코드가 이 값을 지금 시각으로 직접 갱신한다.
    fetched_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
