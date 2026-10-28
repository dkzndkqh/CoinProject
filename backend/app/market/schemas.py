from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CandleResponse(BaseModel):
    """캔들 한 개의 응답 모양. 자바의 응답 DTO(CandleResponse)와 같은 역할이다.
    DB 컬럼 중 Kronos 입력에 필요한 6개만 담는다 (market, timeframe, fetched_at은 뺀다).
    """

    # from_attributes=True: DB에서 읽은 Candle 객체(SQLAlchemy)를 이 클래스로 바로 바꿀 수 있게 한다.
    # 자바에서 엔티티를 DTO로 변환하는 ModelMapper 같은 것을 FastAPI가 알아서 해준다고 보면 된다.
    model_config = ConfigDict(from_attributes=True)

    candle_time: datetime  # 캔들 시작 시각(UTC)
    open: float  # 시가
    high: float  # 고가
    low: float  # 저가
    close: float  # 종가
    volume: float  # 거래량
