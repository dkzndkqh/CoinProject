from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.forecast.models import KronosForecast
from app.forecast.schemas import ForecastCreate


def save_forecast(db: Session, data: ForecastCreate) -> bool:
    """예측 한 건을 저장한다. 같은 (market, horizon, base_time, model_name)이 이미 있으면 저장하지 않는다.
    새로 저장했으면 True, 이미 있어서 무시했으면 False를 돌려준다.

    덮어쓰기(upsert)가 아니라 '있으면 무시'인 이유:
    예측은 8단계 평가에서 채점할 기록이라, 한 번 저장한 값이 나중에 바뀌면 안 된다.
    """
    # model_dump(): 요청 DTO를 dict로 바꾼다. 키 이름이 모델 컬럼 이름과 같아서 그대로 넣을 수 있다.
    # on_conflict_do_nothing: INSERT ... ON CONFLICT DO NOTHING.
    #   기본 키(market, horizon, base_time, model_name)가 겹치면 에러 없이 그냥 건너뛴다.
    #   (candles 저장의 on_conflict_do_update와 반대 동작이다.)
    stmt = (
        insert(KronosForecast)
        .values(**data.model_dump())
        .on_conflict_do_nothing(
            index_elements=["market", "horizon", "base_time", "model_name"]
        )
        # returning: 실제로 들어간 행의 market 값을 돌려받는다.
        # 중복이라 건너뛰면 돌려줄 행이 없다. 이 차이로 저장 여부를 안다.
        .returning(KronosForecast.market)
    )
    result = db.execute(stmt)
    db.commit()
    saved = result.first() is not None  # 행이 왔으면 새로 저장한 것, None이면 건너뜀
    return saved


def get_latest_base_time(db: Session, market: str, model_name: str) -> datetime | None:
    """해당 코인·이름표로 저장된 예측 중 가장 최근 기준 시각을 돌려준다.
    아직 한 건도 없으면 None.

    ai_inference가 시작할 때 "어디까지 계산했는지"를 복원하려고 쓴다.
    """

    # select(func.max(...)): SELECT MAX(base_time) FROM kronos_forecasts WHERE ...
    # 조건에 맞는 행이 하나도 없어도 집계 함수는 에러 없이 NULL(None) 한 행을 돌려준다.
    # 그래서 "없음"을 따로 분기하지 않아도 그대로 None이 반환된다.
    stmt = select(func.max(KronosForecast.base_time)).where(
        KronosForecast.market == market,
        KronosForecast.model_name == model_name,
    )
    # scalar(): 결과의 첫 행 첫 칸의 값 하나만 꺼낸다 (자바 JDBC의 rs.getObject(1)에 가깝다).
    return db.scalar(stmt)


def _horizon_hours(row: KronosForecast) -> int:
    """예측 기간 문자열을 시간 수로 바꾼다. "4h" -> 4, "1d" -> 24.
    문자열 순서로 정렬하면 "12h"가 "1d"보다 앞에 오는 식으로 시간 순서가 어긋나서, 숫자로 바꿔 정렬한다.
    """
    number, unit = int(row.horizon[:-1]), row.horizon[-1]
    return number * (24 if unit == "d" else 1)


def get_latest_forecast(db: Session, market: str, input_tag: str) -> dict | None:
    """코인 하나의 가장 최근 예측 묶음을 돌려준다. 없으면 None.

    input_tag: 어떤 입력 봉으로 낸 예측인지. "4h" 또는 "1d".
        이름(model_name)이 "NeoQuasar/Kronos-base|n300|4h42"처럼 생겨서 "|4h"가 들어 있는 것을 찾는다.
    돌려주는 값: {"model_name", "base_time", "base_price", "horizons": [기간별 예측 목록, 짧은 기간부터]}
    """
    pattern = (
        f"%|{input_tag}%"  # SQL의 LIKE 패턴. % 는 "아무 글자나 여러 개"라는 뜻이다.
    )

    # 1단계: 가장 최근에 올라온 예측 한 건을 골라 '어떤 이름표의 어느 기준 시각'인지 알아낸다.
    # 기준 시각이 같으면 나중에 저장된 것(fetched_at)을 고른다.
    newest = db.execute(
        select(KronosForecast.model_name, KronosForecast.base_time)
        .where(KronosForecast.market == market, KronosForecast.model_name.like(pattern))
        .order_by(KronosForecast.base_time.desc(), KronosForecast.fetched_at.desc())
        .limit(1)
    ).first()
    if newest is None:
        return None  # 이 코인, 이 입력의 예측이 아직 한 건도 없다
    model_name, base_time = newest

    # 2단계: 이름과 기준 시각에 해당하는 모든 행 꺼내기
    rows = db.scalars(
        select(KronosForecast).where(
            KronosForecast.market == market,
            KronosForecast.model_name == model_name,
            KronosForecast.base_time == base_time,
        )
    ).all()

    return {
        "model_name": model_name,
        "base_time": base_time,
        "base_price": rows[0].base_price,  # 기준 시각이 같으면 기준 가격도 모두 같다
        "horizons": [
            {
                "horizon": r.horizon,
                "median": r.median,
                "low_50": r.low_50,
                "high_50": r.high_50,
                "low_80": r.low_80,
                "high_80": r.high_80,
                "up_probability": r.up_probability,
            }
            for r in sorted(rows, key=_horizon_hours)
        ],
    }
