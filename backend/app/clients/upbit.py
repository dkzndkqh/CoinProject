from datetime import UTC, datetime

import httpx

# 업비트 공개 시세 API 공통 주소 (인증키 필요 없음)
BASE_URL = "https://api.upbit.com/v1"

# 응답이 10초안에 안오면 예외를 던짐. 타임아웃이 없으면 무한 대기 발생할 수 있음.
TIMEOUT = 10.0


def _get(path: str, params: dict) -> list[dict]:
    """Upbit에 GET 요청을 보내고 JSON 결과를 반환하는 내부 공통 함수.
    함수 이름 앞의 밑줄(_)은 '이 파일 안에서만 쓰는 내부용'이라는 파이썬 관례다.
    자바의 private 메서드와 비슷하지만, 강제는 아니고 약속일 뿐이다.
    """
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        response = client.get(path, params=params)
        # 4xx, 5xx 응답이면 여기서 예외를 던진다.
        response.raise_for_status()
        # JSON 문자열을 파이썬 list/dict로 변환한다 (자바의 ObjectMapper.readValue와 비슷).
        return response.json()


def _build_params(market: str, count: int, to: datetime | None) -> dict:
    """캔들 요청에 쓸 쿼리 파라미터를 만드는 내부 함수.
    to가 None이면 'to' 키를 아예 넣지 않는다 (최신 캔들부터 받기).
    값이 None인 키를 그대로 보내면 httpx가 'to=' (빈 값)으로 보내서 Upbit가 에러를 낼 수 있기 때문이다.
    """
    params = {"market": market, "count": count}
    if to is not None:
        # Upbit는 UTC 기준 "2025-01-01T00:00:00Z" 형식의 문자열을 받는다.
        # astimezone(UTC)로 어떤 시간대의 datetime이 들어와도 UTC로 바꾼 뒤 포맷한다.
        params["to"] = to.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return params


def get_minute_candles(
    market: str, unit: int, count: int, to: datetime | None = None
) -> list[dict]:
    """분봉 캔들을 가져온다.
    market: "KRW-BTC", "KRW-ETH" 같은 마켓 코드
    unit:   분 단위. Upbit가 지원하는 값은 1, 3, 5, 10, 15, 30, 60, 240
    count:  가져올 개수. Upbit 최대값은 200. 기본값이 없으므로 호출하는 쪽이 반드시 정한다.
    to:     이 시각 '이전'의 캔들을 가져온다 (이 시각의 캔들은 제외). None이면 최신부터.
            과거 데이터를 채우는 백필에서 한 번에 200개씩 거슬러 올라갈 때 쓴다.

    주의: Upbit는 최신 캔들이 맨 앞(리스트 0번)에 오는 내림차순으로 준다.
    지표 계산은 과거 -> 최신 순서가 필요하므로, 나중에 service에서 뒤집는다.
    """
    return _get(f"/candles/minutes/{unit}", _build_params(market, count, to))


def get_daily_candles(
    market: str, count: int, to: datetime | None = None
) -> list[dict]:
    """일봉 캔들을 가져온다."""
    return _get("/candles/days", _build_params(market, count, to))


def get_tickers(markets: list[str]) -> list[dict]:
    """여러 마켓의 현재가를 한 번에 가져온다.
    Upbit는 마켓을 콤마로 이어 붙인 문자열을 받는다. 예: "KRW-BTC,KRW-ETH"
    """
    return _get("/ticker", {"markets": ",".join(markets)})
