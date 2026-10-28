from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.forecast.models import KronosForecast
from app.forecast.schemas import ForecastCreate


def save_forecast(db: Session, data: ForecastCreate) -> bool:
    """예측 한 건을 저장한다. 같은 (market, horizon, base_time)이 이미 있으면 저장하지 않는다.
    새로 저장했으면 True, 이미 있어서 무시했으면 False를 돌려준다.

    덮어쓰기(upsert)가 아니라 '있으면 무시'인 이유:
    예측은 8단계 평가에서 채점할 기록이라, 한 번 저장한 값이 나중에 바뀌면 안 된다.
    """
    # model_dump(): 요청 DTO를 dict로 바꾼다. 키 이름이 모델 컬럼 이름과 같아서 그대로 넣을 수 있다.
    # on_conflict_do_nothing: INSERT ... ON CONFLICT DO NOTHING.
    #   기본 키(market, horizon, base_time)가 겹치면 에러 없이 그냥 건너뛴다.
    #   (candles 저장의 on_conflict_do_update와 반대 동작이다.)
    stmt = (
        insert(KronosForecast)
        .values(**data.model_dump())
        .on_conflict_do_nothing(index_elements=["market", "horizon", "base_time"])
        # returning: 실제로 들어간 행의 market 값을 돌려받는다.
        # 중복이라 건너뛰면 돌려줄 행이 없다. 이 차이로 저장 여부를 안다.
        .returning(KronosForecast.market)
    )
    result = db.execute(stmt)
    db.commit()
    saved = result.first() is not None  # 행이 왔으면 새로 저장한 것, None이면 건너뜀
    return saved
