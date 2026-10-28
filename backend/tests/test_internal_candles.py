from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.exceptions import AppError
from app.main import app
from app.market import service
from app.market.models import Candle

# 테스트 전용 가짜 마켓. 진짜 캔들(KRW-BTC 등)과 섞이지 않고, 끝나면 이 마켓의 행만 지운다.
TEST_MARKET = "TEST-CLOSED"

# "지금"을 이 시각으로 고정한다. 진짜 시계를 쓰면 정각을 넘기는 순간 결과가 바뀌어 테스트가 가끔 실패한다.
NOW = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)

HEADERS = {"X-API-Key": settings.internal_api_key}


class FixedDatetime(datetime):
    """datetime.now()만 NOW로 고정한 가짜 클래스. service 안의 datetime을 이걸로 바꿔치기한다."""

    @classmethod
    def now(cls, tz=None):
        return NOW


def hour(h: int, day: int = 1) -> datetime:
    return datetime(2026, 1, day, h, tzinfo=UTC)


def make_candle(candle_time: datetime, timeframe: str = "1h") -> Candle:
    return Candle(
        market=TEST_MARKET,
        timeframe=timeframe,
        candle_time=candle_time,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=3.0,
    )


def times(candles) -> list[datetime]:
    return [c.candle_time for c in candles]


def _clean(session):
    session.execute(delete(Candle).where(Candle.market == TEST_MARKET))
    session.commit()


@pytest.fixture
def db():
    """실제 DB 세션. 테스트 전후로 가짜 마켓 행만 정리한다."""
    session = SessionLocal()
    _clean(session)
    yield session
    session.rollback()
    _clean(session)
    session.close()


@pytest.fixture
def now_fixed(monkeypatch):
    """service가 보는 '지금'을 2026-01-01 10:30 UTC로 고정한다."""
    monkeypatch.setattr(service, "datetime", FixedDatetime)


@pytest.fixture
def hourly(db):
    """1시간 봉 06,07,08,09,10시를 넣는다. 지금이 10:30이므로 10시 봉은 진행 중이다 (11:00에 마감)."""
    db.add_all([make_candle(hour(h)) for h in (6, 7, 8, 9, 10)])
    db.commit()


# ---------- service: get_closed_candles (실제 DB) ----------


def test_진행_중인_캔들은_빼고_오래된_순서로_준다(hourly, db, now_fixed):
    result = service.get_closed_candles(db, TEST_MARKET, "1h", limit=100)

    assert times(result) == [hour(6), hour(7), hour(8), hour(9)]


def test_limit은_가장_최근_N개를_고른_뒤_오래된_순서로_준다(hourly, db, now_fixed):
    result = service.get_closed_candles(db, TEST_MARKET, "1h", limit=2)

    assert times(result) == [hour(8), hour(9)]


def test_end_time까지만_준다_end_time_캔들은_포함(hourly, db, now_fixed):
    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=100, end_time=hour(8)
    )

    assert times(result) == [hour(6), hour(7), hour(8)]


def test_start_time부터_end_time까지_범위로_거른다(hourly, db, now_fixed):
    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=100, start_time=hour(7), end_time=hour(8)
    )

    assert times(result) == [hour(7), hour(8)]


def test_범위_안이_limit보다_많으면_범위_안에서_최신_N개(hourly, db, now_fixed):
    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=2, start_time=hour(6), end_time=hour(8)
    )

    assert times(result) == [hour(7), hour(8)]


def test_end_time이_미래여도_진행_중_캔들은_안_나간다(hourly, db, now_fixed):
    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=100, end_time=datetime(2030, 1, 1, tzinfo=UTC)
    )

    assert hour(10) not in times(result)
    assert times(result)[-1] == hour(9)


def test_시간대_없는_시각은_UTC로_본다(hourly, db, now_fixed):
    naive = datetime(2026, 1, 1, 8, 0)  # tzinfo 없음

    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=100, end_time=naive
    )

    assert times(result)[-1] == hour(8)


def test_시작이_끝보다_뒤면_AppError(hourly, db, now_fixed):
    with pytest.raises(AppError):
        service.get_closed_candles(
            db, TEST_MARKET, "1h", limit=100, start_time=hour(9), end_time=hour(7)
        )


def test_조건에_맞는_캔들이_없으면_빈_리스트(hourly, db, now_fixed):
    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=100, end_time=datetime(2020, 1, 1, tzinfo=UTC)
    )

    assert result == []


def test_4h_봉은_4시간이_지나야_마감(db, now_fixed):
    # 지금 10:30. 00시 봉은 04시에, 04시 봉은 08시에 마감 -> 포함. 08시 봉은 12시에 마감 -> 진행 중.
    db.add_all([make_candle(hour(h), "4h") for h in (0, 4, 8)])
    db.commit()

    result = service.get_closed_candles(db, TEST_MARKET, "4h", limit=100)

    assert times(result) == [hour(0), hour(4)]


def test_1d_봉은_하루가_지나야_마감(db, now_fixed):
    # 지금 01-01 10:30. 12-30, 12-31 봉은 마감. 01-01 봉은 진행 중.
    db.add_all(
        [
            make_candle(datetime(2025, 12, 30, tzinfo=UTC), "1d"),
            make_candle(datetime(2025, 12, 31, tzinfo=UTC), "1d"),
            make_candle(datetime(2026, 1, 1, tzinfo=UTC), "1d"),
        ]
    )
    db.commit()

    result = service.get_closed_candles(db, TEST_MARKET, "1d", limit=100)

    assert times(result) == [
        datetime(2025, 12, 30, tzinfo=UTC),
        datetime(2025, 12, 31, tzinfo=UTC),
    ]


# ---------- router: GET /api/internal/candles (service는 가짜) ----------


@pytest.fixture
def client():
    """DB 없이 라우터만 검사하는 TestClient. 끝나면 get_db 오버라이드를 원래대로 돌려놓는다.
    (with 없이 쓰므로 스케줄러 같은 lifespan은 실행되지 않는다.)
    """
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


PARAMS = {"market": "KRW-BTC", "timeframe": "4h", "limit": 3}


def test_키가_없으면_401(client):
    response = client.get("/api/internal/candles", params=PARAMS)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_틀린_키면_401(client):
    response = client.get(
        "/api/internal/candles", params=PARAMS, headers={"X-API-Key": "wrong"}
    )

    assert response.status_code == 401


def test_키가_맞으면_200이고_필드_6개만_나간다(client, monkeypatch):
    # DB 객체에는 market, timeframe, fetched_at도 있지만 응답에는 6개 필드만 나가야 한다.
    candle = make_candle(hour(8), "4h")
    monkeypatch.setattr(service, "get_closed_candles", lambda *args, **kwargs: [candle])

    response = client.get("/api/internal/candles", params=PARAMS, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert set(body[0]) == {"candle_time", "open", "high", "low", "close", "volume"}


def test_라우터가_조건을_service에_그대로_넘긴다(client, monkeypatch):
    received = {}

    def fake(db, market, timeframe, limit, start_time, end_time):
        received.update(
            market=market,
            timeframe=timeframe,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )
        return []

    monkeypatch.setattr(service, "get_closed_candles", fake)

    response = client.get(
        "/api/internal/candles",
        params={**PARAMS, "start_time": "2026-01-01T00:00:00Z"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == []
    assert received["market"] == "KRW-BTC"
    assert received["timeframe"] == "4h"
    assert received["limit"] == 3
    assert received["start_time"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert received["end_time"] is None


def test_limit을_안_주면_기본값_400(client, monkeypatch):
    received = {}

    def fake(db, market, timeframe, limit, start_time, end_time):
        received["limit"] = limit
        return []

    monkeypatch.setattr(service, "get_closed_candles", fake)

    client.get(
        "/api/internal/candles",
        params={"market": "KRW-BTC", "timeframe": "1h"},
        headers=HEADERS,
    )

    assert received["limit"] == 400


@pytest.mark.parametrize(
    "bad",
    [
        {"market": "KRW-DOGE"},
        {"timeframe": "5h"},
        {"limit": 0},
        {"limit": 513},
        {"start_time": "어제"},
    ],
)
def test_잘못된_파라미터는_422(client, bad):
    response = client.get(
        "/api/internal/candles", params={**PARAMS, **bad}, headers=HEADERS
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_시작이_끝보다_뒤면_400(client):
    # service의 검사는 DB를 쓰기 전에 일어나므로 가짜 DB(None)로도 확인할 수 있다.
    response = client.get(
        "/api/internal/candles",
        params={
            **PARAMS,
            "start_time": "2026-01-02T00:00:00Z",
            "end_time": "2026-01-01T00:00:00Z",
        },
        headers=HEADERS,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
