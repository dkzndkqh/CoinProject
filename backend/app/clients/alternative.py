import httpx

# Alternative.me 공포·탐욕 지수 API (인증키 필요 없음)
BASE_URL = "https://api.alternative.me"

TIMEOUT = 10.0


def get_fear_greed() -> dict:
    """공포·탐욕 지수의 최신 값 1개를 가져온다. 0(극단적 공포) ~ 100(극단적 탐욕).
    이 지수는 하루에 한 번만 갱신된다.
    응답 예: {"data": [{"value": "48", "value_classification": "Neutral", "timestamp": "1793059200", ...}]}
    리스트에 원소가 1개뿐이라 첫 번째([0])만 돌려준다. 숫자가 문자열("48")로 오는 점은 바이낸스와 같다.
    """
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        response = client.get("/fng/", params={"limit": 1})
        response.raise_for_status()
        return response.json()["data"][0]
