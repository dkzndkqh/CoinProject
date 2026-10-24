from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from app.clients import upbit
from app.core.db import SessionLocal
from app.market import service
from app.market.models import Candle

# 테스트 전용 가짜 마켓 이름. 진짜 캔들(KRW-BTC 등)과 섞이지 않고,
# 테스트 후 이 마켓의 행만 지우기 때문에 실제 데이터는 건드리지 않는다.
TEST_MARKET = "TEST-COIN"


def make_raw(time_utc: str, close: float) -> dict:
    """업비트 응답 dict 한 개를 흉내 낸다 (service가 쓰는 필드만 넣는다)."""
    return {
        "market": TEST_MARKET,
        "candle_date_time_utc": time_utc,
        "opening_price": 100.0,
        "high_price": 120.0,
        "low_price": 90.0,
        "trade_price": close,
        "candle_acc_trade_volume": 5.0,
    }


def _clean(session):
    """가짜 마켓의 행만 지운다."""
    session.execute(delete(Candle).where(Candle.market == TEST_MARKET))
    session.commit()


@pytest.fixture
def db():
    """DB 세션을 만들어 주입하고, 테스트 전후로 가짜 마켓 행을 정리한다.
    yield 앞이 @BeforeEach, 뒤가 @AfterEach에 해당한다 (자바 JUnit 비교).
    """
    session = SessionLocal()
    _clean(session)  # 이전 테스트가 비정상 종료돼 남긴 행이 있을 수 있어서 먼저 지운다
    yield session
    session.rollback()  # 테스트 중 에러로 트랜잭션이 깨졌어도 정리할 수 있게 한다
    _clean(session)
    session.close()


@pytest.fixture
def upbit_calls(monkeypatch):
    """upbit 함수를 가짜로 바꿔서, 어떤 함수가 불렸는지만 기록한다 (네트워크 호출 없음)."""
    calls = []

    def fake_minute(market, unit, count, to=None):
        calls.append(("minute", unit))
        return []

    def fake_daily(market, count, to=None):
        calls.append(("daily", None))
        return []

    monkeypatch.setattr(upbit, "get_minute_candles", fake_minute)
    monkeypatch.setattr(upbit, "get_daily_candles", fake_daily)
    return calls


# 업비트가 준 캔들 한개에 대한 정보를 우리 DB 컬럼 모양으로 바꾸는 테스트
def test_to_row_필드이름을_바꾸고_UTC를_붙인다():
    """[변환 테스트] 업비트 응답 dict 한 개가 우리 candles 컬럼 모양으로 바뀌는지 확인한다.
    DB도 네트워크도 쓰지 않는 가장 단순한 테스트다 (입력 -> 출력만 비교).
    확인하는 것:
    - 업비트 필드 이름이 우리 컬럼 이름으로 바뀐다 (opening_price -> open, trade_price -> close 등)
    - 시간대 없는 문자열 "2025-01-01T00:00:00"이 UTC 표시가 붙은 datetime이 된다
    - market은 응답에서, timeframe은 인자로 받은 값이 들어간다
    """
    row = service._to_row("1h", make_raw("2025-01-01T00:00:00", 110.0))

    assert row == {
        "market": TEST_MARKET,
        "timeframe": "1h",
        "candle_time": datetime(2025, 1, 1, tzinfo=UTC),
        "open": 100.0,
        "high": 120.0,
        "low": 90.0,
        "close": 110.0,
        "volume": 5.0,
    }


# timeframe에 맞는 API를 고르는지 확인 테스트
# parametrize: 같은 테스트를 입력값만 바꿔 여러 번 실행한다 (JUnit @ParameterizedTest)
@pytest.mark.parametrize(
    "timeframe, expected",
    [("1h", ("minute", 60)), ("4h", ("minute", 240)), ("1d", ("daily", None))],
)
def test_fetch_candles는_timeframe에_맞는_API를_고른다(
    upbit_calls, timeframe, expected
):
    service.fetch_candles("KRW-BTC", timeframe, 5)

    assert upbit_calls == [expected]


def test_지원하지_않는_timeframe은_KeyError(upbit_calls):
    # pytest.raises: 이 예외가 나야 통과 (JUnit의 assertThrows)
    with pytest.raises(KeyError):
        service.fetch_candles("KRW-BTC", "5h", 5)


def test_새_캔들은_저장된다(db):
    raws = [
        make_raw("2025-01-01T00:00:00", 110.0),
        make_raw("2025-01-01T01:00:00", 111.0),
    ]

    assert service.save_candles(db, "1h", raws) == 2
    count = db.scalar(
        select(func.count()).select_from(Candle).where(Candle.market == TEST_MARKET)
    )
    assert count == 2


def test_같은_캔들을_다시_저장하면_행은_그대로고_값만바뀐다(db):
    service.save_candles(db, "1h", [make_raw("2025-01-01T00:00:00", 110.0)])
    first_fetched = db.scalar(
        select(Candle.fetched_at).where(Candle.market == TEST_MARKET)
    )

    # 같은 키(market, timeframe, candle_time)에 종가만 바꿔서 다시 저장
    service.save_candles(db, "1h", [make_raw("2025-01-01T00:00:00", 999.0)])

    rows = db.scalars(select(Candle).where(Candle.market == TEST_MARKET)).all()
    assert len(rows) == 1  # 중복행이 생기지 않았음
    assert rows[0].close == 999.0  # 값이 덮어써짐
    assert rows[0].fetched_at > first_fetched  # 수집 시각이 갱신됨


def test_빈_목록은_0을_돌려준다(db):
    """[경계값 테스트] 저장할 캔들이 없을 때(빈 리스트) 에러 없이 0을 돌려주는지 확인한다.
    빈 목록으로 INSERT 문을 만들면 에러가 나기 때문에 함수 앞부분에서 미리 막아 둔 부분이다.
    업비트가 빈 응답을 주는 경우에 대비한다.
    """
    assert service.save_candles(db, "1h", []) == 0
