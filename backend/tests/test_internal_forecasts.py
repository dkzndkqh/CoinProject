from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.forecast import service
from app.forecast.models import KronosForecast
from app.forecast.schemas import ForecastCreate
from app.main import app

# 테스트로 넣은 행에만 붙이는 표시. 시장은 KRW-BTC로 고정돼 있어(스키마가 막음) 진짜 예측과 섞이지 않게
# 이 모델 이름과 아주 오래된 기준 시각(2000년)을 쓰고, 끝나면 이 모델 이름의 행만 지운다.
TEST_MODEL = "pytest"
BASE_TIME = datetime(2000, 1, 1, 12, tzinfo=UTC)

HEADERS = {"X-API-Key": settings.internal_api_key}

VALID = {
    "market": "KRW-BTC",
    "horizon": "7d",
    "base_time": BASE_TIME,
    "base_price": 150_000_000.0,
    "median": 152_000_000.0,
    "low_50": 148_500_000.0,
    "high_50": 155_000_000.0,
    "low_80": 142_000_000.0,
    "high_80": 163_000_000.0,
    "up_probability": 0.54,
    "model_name": TEST_MODEL,
}


def make(**override) -> ForecastCreate:
    return ForecastCreate(**{**VALID, **override})


def _clean(session):
    session.execute(
        delete(KronosForecast).where(KronosForecast.model_name == TEST_MODEL)
    )
    session.commit()


@pytest.fixture
def db():
    session = SessionLocal()
    _clean(session)
    yield session
    session.rollback()
    _clean(session)
    session.close()


def count_test_rows(db) -> int:
    return db.scalar(
        select(func.count())
        .select_from(KronosForecast)
        .where(KronosForecast.model_name == TEST_MODEL)
    )


# ---------- 스키마: ForecastCreate 입력 검증 (DB 없음) ----------


def test_정상_값은_통과한다():
    assert make().market == "KRW-BTC"


@pytest.mark.parametrize("horizon", ["4h", "1d", "7d", "30d"])
def test_기간_형식이_맞으면_통과한다(horizon):
    assert make(horizon=horizon).horizon == horizon


def test_같은_값이어도_순서는_통과한다():
    # <= 로 검사하므로 low_50 == median 처럼 값이 같은 경우도 허용한다.
    assert make(low_50=152_000_000.0, high_50=152_000_000.0)


@pytest.mark.parametrize(
    "override",
    [
        {"low_50": 160_000_000.0},  # low_50이 median보다 큼 (순서 틀림)
        {"low_80": 149_000_000.0},  # low_80이 low_50보다 큼
        {"high_80": 154_000_000.0},  # high_80이 high_50보다 작음
        {"median": 100.0},  # median이 low_50보다 작음
        {"base_time": datetime(2000, 1, 1, 12)},  # 시간대 없음
        {"up_probability": 1.5},
        {"up_probability": -0.1},
        {"median": -1.0},
        {"base_price": 0.0},
        {"base_price": float("inf")},
        {"base_price": float("nan")},
        {"horizon": "weekly"},
        {"horizon": ""},
        {"horizon": "7"},
        {"market": "KRW-DOGE"},
        {"model_name": ""},
        {"model_name": "x" * 51},
    ],
)
def test_잘못된_값은_검증에서_거절된다(override):
    with pytest.raises(ValidationError):
        make(**override)


# ---------- service: save_forecast (실제 DB) ----------


def test_새_예측은_저장된다(db):
    assert service.save_forecast(db, make()) is True
    assert count_test_rows(db) == 1


def test_같은_키로_다시_올리면_저장하지_않는다(db):
    service.save_forecast(db, make())

    assert service.save_forecast(db, make()) is False
    assert count_test_rows(db) == 1


def test_같은_키면_처음_값이_그대로_남는다(db):
    # 예측은 채점할 기록이라 덮어쓰면 안 된다.
    service.save_forecast(db, make(median=152_000_000.0))
    service.save_forecast(db, make(median=153_000_000.0))

    saved = db.scalars(
        select(KronosForecast).where(KronosForecast.model_name == TEST_MODEL)
    ).one()
    assert saved.median == 152_000_000.0


def test_기준_시각이_다르면_새_행이다(db):
    service.save_forecast(db, make())

    assert service.save_forecast(
        db, make(base_time=datetime(2000, 1, 1, 13, tzinfo=UTC))
    )
    assert count_test_rows(db) == 2


def test_기간이_다르면_새_행이다(db):
    service.save_forecast(db, make(horizon="7d"))

    assert service.save_forecast(db, make(horizon="1d"))
    assert count_test_rows(db) == 2


def test_저장된_값과_수집_시각이_채워진다(db):
    service.save_forecast(db, make())

    saved = db.scalars(
        select(KronosForecast).where(KronosForecast.model_name == TEST_MODEL)
    ).one()
    assert saved.market == "KRW-BTC"
    assert saved.horizon == "7d"
    assert saved.base_time == BASE_TIME
    assert saved.up_probability == 0.54
    assert saved.fetched_at is not None  # DB가 now()로 채움


# ---------- router: POST /api/internal/forecasts (service는 가짜) ----------


@pytest.fixture
def client():
    """DB 없이 라우터만 검사하는 TestClient. 끝나면 get_db 오버라이드를 원래대로 돌려놓는다."""
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


# JSON으로 보낼 본문 (datetime은 문자열로)
BODY = {**VALID, "base_time": "2026-01-01T12:00:00Z"}


def test_키가_없으면_401(client):
    response = client.post("/api/internal/forecasts", json=BODY)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_틀린_키면_401(client):
    response = client.post(
        "/api/internal/forecasts", json=BODY, headers={"X-API-Key": "wrong"}
    )

    assert response.status_code == 401


def test_저장되면_saved_true(client, monkeypatch):
    monkeypatch.setattr(service, "save_forecast", lambda db, data: True)

    response = client.post("/api/internal/forecasts", json=BODY, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"saved": True}


def test_이미_있으면_saved_false(client, monkeypatch):
    monkeypatch.setattr(service, "save_forecast", lambda db, data: False)

    response = client.post("/api/internal/forecasts", json=BODY, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"saved": False}


def test_요청_본문이_검증된_객체로_service에_전달된다(client, monkeypatch):
    received = {}

    def fake(db, data):
        received["data"] = data
        return True

    monkeypatch.setattr(service, "save_forecast", fake)

    client.post("/api/internal/forecasts", json=BODY, headers=HEADERS)

    data = received["data"]
    assert isinstance(data, ForecastCreate)
    assert data.horizon == "7d"
    assert data.base_time == datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "bad",
    [
        {"low_50": 160_000_000.0},
        {"base_time": "2026-01-01T12:00:00"},  # 시간대 없음
        {"up_probability": 1.5},
        {"median": -1},
        {"horizon": "weekly"},
        {"market": "KRW-DOGE"},
    ],
)
def test_잘못된_본문은_422이고_service는_호출되지_않는다(client, monkeypatch, bad):
    def must_not_call(db, data):
        raise AssertionError("검증에 실패했는데 service가 호출됨")

    monkeypatch.setattr(service, "save_forecast", must_not_call)

    response = client.post(
        "/api/internal/forecasts", json={**BODY, **bad}, headers=HEADERS
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_필수_필드가_빠지면_422(client):
    body = {k: v for k, v in BODY.items() if k != "horizon"}

    response = client.post("/api/internal/forecasts", json=body, headers=HEADERS)

    assert response.status_code == 422
