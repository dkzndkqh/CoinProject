from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.agent import service as agent_service
from app.core.db import SessionLocal
from app.forecast import service as forecast_service
from app.forecast.models import KronosForecast
from app.market import service as market_service
from app.market.models import Candle

# 테스트 전용 가짜 마켓. 진짜 데이터(KRW-BTC 등)와 섞이지 않고, 끝나면 이 마켓의 행만 지운다.
TEST_MARKET = "TEST-AGENT"

BASE_TIME = datetime(2026, 10, 31, 8, 0, tzinfo=UTC)  # = 17:00 KST
NOW = BASE_TIME + timedelta(hours=3)  # 예측이 3시간 지난 시점


@pytest.fixture
def db():
    """DB 세션을 주고, 테스트 전후로 가짜 마켓 행만 지운다."""
    session = SessionLocal()

    def clean():
        session.execute(delete(Candle).where(Candle.market == TEST_MARKET))
        session.execute(
            delete(KronosForecast).where(KronosForecast.market == TEST_MARKET)
        )
        session.commit()

    clean()
    yield session
    session.rollback()
    clean()
    session.close()


def add_forecast(db, horizon, input_tag, base_time=BASE_TIME, **override):
    """가짜 예측 한 행을 넣는다. input_tag는 model_name 이름표에 들어가는 "4h"/"1d"."""
    row = {
        "market": TEST_MARKET,
        "horizon": horizon,
        "base_time": base_time,
        "base_price": 100.0,
        "median": 110.0,
        "low_50": 105.0,
        "high_50": 115.0,
        "low_80": 95.0,
        "high_80": 125.0,
        "up_probability": 0.7,
        "model_name": f"test|n1|{input_tag}",
    }
    db.add(KronosForecast(**{**row, **override}))
    db.commit()


def add_hour_candle(db, candle_time, close):
    db.add(
        Candle(
            market=TEST_MARKET,
            timeframe="1h",
            candle_time=candle_time,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
        )
    )
    db.commit()


# ---------- 순수 함수 (DB 없음) ----------


def test_kst_text는_UTC를_한국시간으로_바꾼다():
    assert agent_service._kst_text(BASE_TIME) == "2026-10-31 17:00 KST"


def test_pct_vs는_위는_양수_아래는_음수():
    assert agent_service._pct_vs(110.0, 100.0) == 10.0
    assert agent_service._pct_vs(95.0, 100.0) == -5.0


def test_horizon_delta는_시간과_일을_구분한다():
    assert agent_service._horizon_delta("12h") == timedelta(hours=12)
    assert agent_service._horizon_delta("2d") == timedelta(days=2)


def test_shape_forecast는_목표시각과_퍼센트를_계산한다():
    fc = {
        "base_time": BASE_TIME,
        "base_price": 100.0,
        "horizons": [
            {
                "horizon": "1d",
                "median": 110.0,
                "low_50": 105.0,
                "high_50": 115.0,
                "low_80": 90.0,
                "high_80": 130.0,
                "up_probability": 0.666,
            }
        ],
    }
    # 현재가 100 기준
    shaped = agent_service._shape_forecast(fc, 100.0, NOW)

    assert shaped["base_time_kst"] == "2026-10-31 17:00 KST"
    assert shaped["hours_ago"] == 3.0
    h = shaped["horizons"]["1d"]
    assert h["target_time_kst"] == "2026-11-01 17:00 KST"  # 기준 시각 + 24시간
    assert h["hours_from_now"] == 21.0  # 24 - 3
    assert h["median_vs_price_pct"] == 10.0
    assert h["range_80_vs_price_pct"] == [-10.0, 30.0]
    assert h["up_probability"] == 0.67
    assert h["down_probability"] == 0.33  # 반올림한 값 기준이라 합이 1


# ---------- forecast: get_latest_forecast ----------


def test_get_latest_forecast는_없으면_None(db):
    assert forecast_service.get_latest_forecast(db, TEST_MARKET, "4h") is None


def test_get_latest_forecast는_입력별로_가장_최근_묶음을_시간순으로_준다(db):
    old = BASE_TIME - timedelta(hours=4)
    # 4h 입력: 오래된 묶음 1개 + 최신 묶음 3개(일부러 섞인 순서로 저장)
    add_forecast(db, "4h", "4h", base_time=old)
    for horizon in ("1d", "4h", "12h"):
        add_forecast(db, horizon, "4h")
    # 1d 입력은 따로 있어도 4h 조회에 섞이지 않아야 한다
    add_forecast(db, "1d", "1d", median=999.0)

    fc = forecast_service.get_latest_forecast(db, TEST_MARKET, "4h")

    assert fc["base_time"] == BASE_TIME
    assert fc["model_name"] == "test|n1|4h"
    # "12h"가 "1d"보다 앞에 오는 문자열 순서가 아니라 시간 순서여야 한다
    assert [h["horizon"] for h in fc["horizons"]] == ["4h", "12h", "1d"]
    assert all(h["median"] != 999.0 for h in fc["horizons"])


# ---------- market: get_recent_returns ----------


def test_get_recent_returns는_기간별_퍼센트를_계산한다(db, monkeypatch):
    # 시간이 흘러 결과가 흔들리지 않도록 now를 고정한다
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(market_service, "datetime", FixedDatetime)

    # 24시간 전 target = NOW - 24h. 그 1시간 전에 시작한 캔들이 마지막으로 마감된 봉이다.
    add_hour_candle(db, NOW - timedelta(hours=25), close=100.0)

    returns = market_service.get_recent_returns(db, TEST_MARKET, 110.0)

    assert returns["24h"] == 10.0
    # 7일, 30일 전 캔들은 없으니 계산하지 않는다
    assert returns["7d"] is None
    assert returns["30d"] is None


def test_get_recent_returns는_너무_오래된_캔들이면_None(db, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(market_service, "datetime", FixedDatetime)

    # target보다 3시간 넘게 이전 캔들만 있으면 "24시간 변화"가 아니므로 None
    add_hour_candle(db, NOW - timedelta(hours=24 + 5), close=100.0)

    assert market_service.get_recent_returns(db, TEST_MARKET, 110.0)["24h"] is None


# ---------- agent: build_agent_input ----------


def fake_judgement():
    return {
        "4h": {"price": 100.0, "price_time": "2026-10-31T08:00:00+00:00"},
        "1d": {"price": 100.0, "price_time": "2026-10-31T00:00:00+00:00"},
    }


def test_build_agent_input은_캔들이_모자라면_None(db, monkeypatch):
    monkeypatch.setattr(market_service, "get_indicator_judgement", lambda d, m: None)

    assert agent_service.build_agent_input(db, TEST_MARKET) is None


def test_build_agent_input은_예측이_없는_입력은_None으로_둔다(db, monkeypatch):
    monkeypatch.setattr(
        market_service, "get_indicator_judgement", lambda d, m: fake_judgement()
    )
    add_forecast(db, "4h", "4h")  # 4h 입력만 있고 1d 입력은 없다

    result = agent_service.build_agent_input(db, TEST_MARKET)

    assert result["price"] == 100.0
    assert result["forecasts"]["4h"] is not None
    assert result["forecasts"]["1d"] is None
    assert set(result["recent_returns_pct"]) == {"24h", "7d", "30d"}
    assert set(result["indicators"]) == {"4h", "1d"}
