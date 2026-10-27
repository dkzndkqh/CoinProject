from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from app.clients import alternative, binance
from app.core.db import SessionLocal
from app.market import service
from app.market.models import MarketSnapshot

# 진짜 데이터(KRW-BTC 등)와 섞이지 않게 테스트 전용 마켓 이름을 쓴다.
TEST_MARKET = "TEST-COIN"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


# ─────────────── floor_time ───────────────


@pytest.mark.parametrize(
    "minute, second, expected_minute",
    [(7, 30, 0), (15, 0, 15), (29, 59, 15), (59, 59, 45)],
)
def test_floor_time은_15분_칸으로_내린다(minute, second, expected_minute):
    dt = datetime(2026, 1, 1, 12, minute, second, 123456, tzinfo=UTC)

    result = service.floor_time(dt, 15)

    assert result == datetime(2026, 1, 1, 12, expected_minute, tzinfo=UTC)


# ─────────────── fetch_snapshot_rows (외부 API는 가짜) ───────────────


@pytest.fixture
def fake_apis(monkeypatch):
    """외부 API 3개를 가짜 함수로 바꾼다. 값은 실제처럼 문자열로 준다."""
    monkeypatch.setattr(
        binance, "get_open_interest", lambda symbol: {"openInterest": "100.5"}
    )
    monkeypatch.setattr(
        binance, "get_long_short_ratio", lambda symbol: {"longShortRatio": "2.5"}
    )
    monkeypatch.setattr(alternative, "get_fear_greed", lambda: {"value": "48"})


def _fail(*args):
    raise RuntimeError("외부 API 장애")


def test_정상이면_문자열을_숫자로_바꿔_코인마다_한_행씩_만든다(fake_apis):
    rows = service.fetch_snapshot_rows(["KRW-BTC", "KRW-ETH"], T0)

    expected = {
        "snapshot_time": T0,
        "open_interest": 100.5,
        "long_short_ratio": 2.5,
        "fear_greed": 48,
    }
    assert rows == [
        {"market": "KRW-BTC", **expected},
        {"market": "KRW-ETH", **expected},
    ]


def test_롱숏비율이_실패해도_나머지_값은_남는다(fake_apis, monkeypatch):
    monkeypatch.setattr(binance, "get_long_short_ratio", _fail)

    rows = service.fetch_snapshot_rows(["KRW-BTC"], T0)

    assert rows[0]["long_short_ratio"] is None
    assert rows[0]["open_interest"] == 100.5
    assert rows[0]["fear_greed"] == 48


def test_공포탐욕이_실패하면_모든_코인의_그_값만_None이다(fake_apis, monkeypatch):
    monkeypatch.setattr(alternative, "get_fear_greed", _fail)

    rows = service.fetch_snapshot_rows(["KRW-BTC", "KRW-ETH"], T0)

    assert [r["fear_greed"] for r in rows] == [None, None]
    assert [r["open_interest"] for r in rows] == [100.5, 100.5]


def test_응답_모양이_이상해도_그_값만_None이다(fake_apis, monkeypatch):
    # openInterest 키가 없는 응답 -> KeyError가 나도 _safe가 받아서 None으로 처리한다.
    monkeypatch.setattr(binance, "get_open_interest", lambda symbol: {})

    rows = service.fetch_snapshot_rows(["KRW-BTC"], T0)

    assert rows[0]["open_interest"] is None
    assert rows[0]["long_short_ratio"] == 2.5


# ─────────────── save_snapshots (진짜 DB) ───────────────


def _clean(session):
    session.execute(delete(MarketSnapshot).where(MarketSnapshot.market == TEST_MARKET))
    session.commit()


@pytest.fixture
def db():
    """DB 세션을 주고, 테스트 전후로 테스트 전용 마켓의 행을 지운다."""
    session = SessionLocal()
    _clean(session)
    yield session
    session.rollback()
    _clean(session)
    session.close()


def make_row(**override):
    row = {
        "market": TEST_MARKET,
        "snapshot_time": T0,
        "open_interest": 100.0,
        "long_short_ratio": 2.0,
        "fear_greed": 50,
    }
    return {**row, **override}  # override로 일부 값만 바꿔 쓴다


def test_빈_목록은_0을_돌려준다(db):
    assert service.save_snapshots(db, []) == 0


def test_새_스냅샷은_저장된다(db):
    assert service.save_snapshots(db, [make_row()]) == 1

    saved = db.get(MarketSnapshot, (TEST_MARKET, T0))
    assert (saved.open_interest, saved.long_short_ratio, saved.fear_greed) == (
        100.0,
        2.0,
        50,
    )


def test_같은_칸을_다시_저장하면_행은_하나고_값만_바뀐다(db):
    service.save_snapshots(db, [make_row(open_interest=100.0)])
    service.save_snapshots(db, [make_row(open_interest=200.0)])

    count = db.scalar(
        select(func.count())
        .select_from(MarketSnapshot)
        .where(MarketSnapshot.market == TEST_MARKET)
    )
    assert count == 1
    assert db.get(MarketSnapshot, (TEST_MARKET, T0)).open_interest == 200.0


def test_재수집에서_실패한_값은_기존_값을_지우지_않는다(db):
    service.save_snapshots(db, [make_row()])
    # 두 번째 수집: 미결제약정, 공포·탐욕은 실패(None), 롱숏 비율만 새 값
    service.save_snapshots(
        db,
        [make_row(open_interest=None, long_short_ratio=3.0, fear_greed=None)],
    )

    saved = db.get(MarketSnapshot, (TEST_MARKET, T0))
    assert saved.open_interest == 100.0  # 기존 값 유지
    assert saved.long_short_ratio == 3.0  # 새 값으로 갱신
    assert saved.fear_greed == 50  # 기존 값 유지
