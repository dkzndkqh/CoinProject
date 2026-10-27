import httpx

# 바이낸스 USDT-M 선물 공개 API 주소 (인증키 필요 없음).
# 현물(api.binance.com)이 아니라 선물(fapi)이다. 미결제약정과 롱숏 비율은 선물 시장의 값이기 때문이다.
BASE_URL = "https://fapi.binance.com"

# 10초안에 응답이 없으면 예외
TIMEOUT = 10.0


def _get(path: str, params: dict) -> dict | list:
    """바이낸스에 GET 요청을 보내고 JSON 결과를 돌려주는 내부 공통 함수.
    (upbit.py의 _get과 같은 구조다. 응답이 dict일 때도 list일 때도 있어서 반환 타입이 둘 다 가능하다.)
    """
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        response = client.get(path, params=params)
        # 4xx, 5xx 응답이면 예외처리
        response.raise_for_status()
        return response.json()


def get_open_interest(symbol: str) -> dict:
    """미결제약정(아직 청산되지 않은 선물 계약 총량)을 가져온다.
    symbol: 바이낸스 선물 심볼. "BTCUSDT", "ETHUSDT" 처럼 쓴다 (업비트의 "KRW-BTC"와 다르다).
    응답 예: {"symbol": "BTCUSDT", "openInterest": "97714.439", "time": 1793088206830}
    주의: 숫자가 문자열("97714.439")로 온다. 숫자로 바꾸는 일은 service가 한다.
    """
    return _get("/fapi/v1/openInterest", {"symbol": symbol})


def get_long_short_ratio(symbol: str) -> dict:
    """전체 계정 기준 롱숏 비율의 최신 값 1개를 가져온다.
    period="15m": 15분 단위로 집계된 값. 우리 수집 주기와 맞춘다.
    limit=1: 가장 최근 1개만 받는다.
    응답은 리스트로 오는데 (예: [{"longAccount": "0.7058", "longShortRatio": "2.3990", ...}])
    원소가 1개뿐이라 첫 번째([0])만 돌려준다.
    """
    data = _get(
        "/futures/data/globalLongShortAccountRatio",
        {"symbol": symbol, "period": "15m", "limit": 1},
    )

    return data[0]
