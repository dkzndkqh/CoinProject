from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
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
    timeframe: Mapped[str] = mapped_column(String(10), primary_key=True)

    # candle_time: 이 캔들이 시작되는 시각 (UTC 기준).
    # timezone=True: 시간대 정보를 같이 저장한다. 시간대 없는 시각은 KST/UTC가 섞여 버그가 나기 쉽다.
    candle_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

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
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MarketSnapshot(Base):
    """시장 지표 스냅샷 한 개 = 테이블 한 행.
    캔들이 '구간의 OHLCV'라면 이것은 '이 시각의 값'이다.
    15분마다 코인별로 한 행씩 쌓이고, 에이전트가 최신 행과 과거 행의 변화를 읽는다.
    """

    __tablename__ = "market_snapshots"

    # --- 기본 키 : market + snapshot_time 복합키 ---
    # 같은 코인, 같은 시각의 스냅샷은 한 행만 존재 (재수집하면 덮어쓰기)
    market: Mapped[str] = mapped_column(String(20), primary_key=True)

    # snapshot_time: 수집 시각을 15분 단위로 내린 값 (예: 12:07에 수집 -> 12:00).
    # 실제 수집 시각이 매번 조금씩 달라도 시간 칸이 일정하게 맞춰져서 캔들과 비교하기 쉽다.
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )

    # --- 지표 값 ---
    # Mapped[float | None]: "float 또는 None"이라는 뜻이고, DB 컬럼이 NULL을 허용한다.
    # 자바에서 Double(래퍼 타입, null 가능)을 쓰는 것과 같다. double(기본형)은 null이 안 된다.
    # 외부 API 하나가 실패해도 나머지 값은 저장해야 하므로 지표 컬럼은 모두 NULL을 허용한다.

    # 미결제약정: 아직 청산되지 않은 선물 계약 총량 (코인 개수 기준, 바이낸스)
    open_interest: Mapped[float | None] = mapped_column(Float)
    # 롱숏 비율: 전체 계정 기준 롱 계정 수 / 숏 계정 수 (바이낸스)
    long_short_ratio: Mapped[float | None] = mapped_column(Float)
    # 공포·탐욕 지수: 0(극단적 공포) ~ 100(극단적 탐욕). 코인 공통값이라 BTC, ETH 행에 같은 값을 넣는다.
    fear_greed: Mapped[int | None] = mapped_column(Integer)

    # 실제로 값을 받아 저장한 시각 (candles의 fetched_at과 같은 역할)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
