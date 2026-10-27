import httpx
import pytest

from app.clients import alternative, binance


@pytest.fixture
def fake_http(monkeypatch):
    """인터넷 대신 가짜 응답을 돌려주고, 어떤 주소와 파라미터로 불렀는지 기록한다.
    테스트에서 fake_http["body"]에 돌려줄 응답을 넣고 쓴다.
    """

    fake = {"calls": [], "body": None}

    def fake_get(self, url, params=None):
        fake["calls"].append({"url": url, "params": params})
        return httpx.Response(
            200, json=fake["body"], request=httpx.Request("GET", f"https://x{url}")
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    return fake


def test_미결제약정은_symbol을_보내고_응답을_그대로_돌려준다(fake_http):
    fake_http["body"] = {"symbol": "BTCUSDT", "openInterest": "97714.439"}

    result = binance.get_open_interest("BTCUSDT")

    assert fake_http["calls"][0]["url"] == "/fapi/v1/openInterest"
    assert fake_http["calls"][0]["params"] == {"symbol": "BTCUSDT"}
    assert result == {"symbol": "BTCUSDT", "openInterest": "97714.439"}


def test_롱숏비율은_15분_최신1개를_요청하고_첫_원소를_돌려준다(fake_http):
    # 바이낸스는 리스트로 주는데, 우리는 첫 번째 값만 꺼내 쓴다.
    fake_http["body"] = [{"symbol": "BTCUSDT", "longShortRatio": "2.3990"}]

    result = binance.get_long_short_ratio("BTCUSDT")

    assert fake_http["calls"][0]["url"] == "/futures/data/globalLongShortAccountRatio"
    assert fake_http["calls"][0]["params"] == {
        "symbol": "BTCUSDT",
        "period": "15m",
        "limit": 1,
    }
    assert result == {"symbol": "BTCUSDT", "longShortRatio": "2.3990"}


def test_공포탐욕은_data의_첫_원소를_돌려준다(fake_http):
    fake_http["body"] = {"data": [{"value": "48", "value_classification": "Neutral"}]}

    result = alternative.get_fear_greed()

    # 주소 끝의 '/'가 빠지면 서버가 리다이렉트해서 실패하므로 꼭 확인한다.
    assert fake_http["calls"][0]["url"] == "/fng/"
    assert fake_http["calls"][0]["params"] == {"limit": 1}
    assert result == {"value": "48", "value_classification": "Neutral"}
