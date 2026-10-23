import httpx
import pytest

from app.clients import upbit


@pytest.fixture
def captured(monkeypatch):
    """httpx.Client.get 호출을 가로채서 요청 내용을 기록하는 가짜 설정.

    @pytest.fixture는 테스트 함수에 자동으로 주입되는 준비물이다.
    자바 JUnit의 @BeforeEach + Mockito 목 객체를 합친 것과 비슷하다.
    monkeypatch는 pytest가 주는 도구로, 테스트가 끝나면 원래대로 복구해 준다.
    """
    calls = []

    def fake_get(self, url, params=None):

        # 실제로 네트워크를 보내지 않고, 어떤 URL과 파라미터로 불렀는지만 기록한다
        calls.append({"url": url, "params": params})
        # 가짜 응답: 200 상태코드 + 빈 JSON 리스트.
        # request는 raise_for_status()가 필요로 해서 넣는다.
        return httpx.Response(
            200, json=[], request=httpx.Request("GET", f"https://x{url}")
        )

    # httpx.Client의 get 메서드를 fake_get으로 교체한다.
    monkeypatch.setattr(httpx.Client, "get", fake_get)
    return calls


def test_분봉은_unit이_경로에_들어가고_market_count를_보낸다(captured):
    upbit.get_minute_candles("KRW-BTC", 60, 3)
    assert captured[0]["url"] == "/candles/minutes/60"
    assert captured[0]["params"] == {"market": "KRW-BTC", "count": 3}


def test_일봉은_market_count를_보낸다(captured):
    upbit.get_daily_candles("KRW-ETH", 2)

    assert captured[0]["url"] == "/candles/days"
    assert captured[0]["params"] == {"market": "KRW-ETH", "count": 2}


def test_티커는_markets_파라미터에_콤마로_이어_붙인다(captured):
    upbit.get_tickers(["KRW-BTC", "KRW-ETH"])

    assert captured[0]["url"] == "/ticker"
    assert captured[0]["params"] == {"markets": "KRW-BTC,KRW-ETH"}
