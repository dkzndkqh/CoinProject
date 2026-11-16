from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.db import SessionLocal, get_db
from app.main import app
from app.market import service
from app.market.models import Candle

# 공개 캔들 API(GET /api/market/{coin}/candles)와 service의 include_open 스위치 테스트.
TEST_MARKET = "TEST-PUBLIC"

# "지금"을 고정한다. 10시 봉은 10:30 시점에 진행 중이다 (11:00에 마감).
NOW = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def hour(h: int) -> datetime:
    return datetime(2026, 1, 1, h, tzinfo=UTC)


def make_candle(candle_time: datetime) -> Candle:
    return Candle(
        market=TEST_MARKET,
        timeframe="1h",
        candle_time=candle_time,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=3.0,
    )


def _clean(session):
    session.execute(delete(Candle).where(Candle.market == TEST_MARKET))
    session.commit()


@pytest.fixture
def db():
    session = SessionLocal()
    _clean(session)
    session.add_all([make_candle(hour(h)) for h in (8, 9, 10)])
    session.commit()
    yield session
    session.rollback()
    _clean(session)
    session.close()


@pytest.fixture
def now_fixed(monkeypatch):
    monkeypatch.setattr(service, "datetime", FixedDatetime)


# ---------- service: include_open (실제 DB) ----------


def test_include_open이_True면_진행_중_캔들도_준다(db, now_fixed):
    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=100, include_open=True
    )

    assert [c.candle_time for c in result] == [hour(8), hour(9), hour(10)]


def test_include_open_기본값은_진행_중_캔들을_뺀다(db, now_fixed):
    result = service.get_closed_candles(db, TEST_MARKET, "1h", limit=100)

    assert [c.candle_time for c in result] == [hour(8), hour(9)]


def test_include_open이어도_end_time_이후는_안_준다(db, now_fixed):
    result = service.get_closed_candles(
        db, TEST_MARKET, "1h", limit=100, end_time=hour(9), include_open=True
    )

    assert [c.candle_time for c in result] == [hour(8), hour(9)]


def test_include_open이어도_시간대_없는_end_time을_UTC로_본다(db, now_fixed):
    # tzinfo 없는 값과 있는 값을 비교하면 TypeError가 나던 경로다.
    result = service.get_closed_candles(
        db,
        TEST_MARKET,
        "1h",
        limit=100,
        end_time=datetime(2026, 1, 1, 9),
        include_open=True,
    )

    assert [c.candle_time for c in result] == [hour(8), hour(9)]


# ---------- router: GET /api/market/{coin}/candles (service는 가짜) ----------


@pytest.fixture
def client():
    """DB 없이 라우터만 검사한다. 끝나면 get_db 오버라이드를 원래대로 돌려놓는다."""
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def test_인증_없이_200이고_필드_6개만_나간다(client, monkeypatch):
    candle = make_candle(hour(8))
    monkeypatch.setattr(service, "get_closed_candles", lambda *a, **kw: [candle])

    response = client.get("/api/market/btc/candles", params={"timeframe": "1h"})

    assert response.status_code == 200
    body = response.json()
    assert set(body[0]) == {"candle_time", "open", "high", "low", "close", "volume"}


def test_라우터는_코인을_마켓으로_바꾸고_include_open을_켜서_넘긴다(
    client, monkeypatch
):
    received = {}

    def fake(db, market, timeframe, limit, **kwargs):
        received.update(market=market, timeframe=timeframe, limit=limit, **kwargs)
        return []

    monkeypatch.setattr(service, "get_closed_candles", fake)

    response = client.get(
        "/api/market/ETH/candles",  # 대소문자 무관
        params={"timeframe": "4h", "end_time": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 200
    assert response.json() == []
    assert received["market"] == "KRW-ETH"
    assert received["timeframe"] == "4h"
    assert received["limit"] == 300  # 기본값
    assert received["end_time"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert received["include_open"] is True


def test_지원하지_않는_코인은_404(client):
    response = client.get("/api/market/doge/candles", params={"timeframe": "1h"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "params",
    [
        {},  # timeframe 없음
        {"timeframe": "5m"},  # 허용 안 되는 봉
        {"timeframe": "1h", "limit": 0},
        {"timeframe": "1h", "limit": 1001},
    ],
)
def test_잘못된_입력은_422(client, params):
    response = client.get("/api/market/btc/candles", params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
