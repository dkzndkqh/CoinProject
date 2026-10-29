import httpx
import pandas as pd

from config import settings


def get_candles(
    market: str,
    timeframe: str,
    limit: int = 512,
    start_time=None,  # 이 시각 이후 캔들만 (선택)
    end_time=None,  # 이 시각까지의 캔들만 (선택). 과거 시점으로 돌아가 볼 때 쓴다
) -> pd.DataFrame:
    """백엔드 DB의 마감 캔들을 받아 DataFrame으로 돌려준다 (오래된 순).
    Kronos 입력으로 쓰려고 candle_time을 UTC 시각 컬럼으로 바꿔 둔다.
    """
    params = {"market": market, "timeframe": timeframe, "limit": limit}
    # 값이 있을 때만 붙인다. 안 주면 보내지 않아서 기존처럼 '가장 최근 캔들'을 받는다.
    if start_time is not None:
        params["start_time"] = start_time.isoformat()
    if end_time is not None:
        params["end_time"] = end_time.isoformat()

    # httpx.get: 자바의 RestClient.get()과 같다. params는 쿼리스트링(?market=...&limit=...)이 된다.
    # X-API-Key 헤더로 인증한다. 백엔드가 이 키를 .env 값과 비교한다.
    resp = httpx.get(
        f"{settings.backend_url}/api/internal/candles",
        params=params,
        headers={"X-API-Key": settings.internal_api_key},
        timeout=10,
    )
    # 4xx, 5xx면 예외를 던진다 (조용히 빈 데이터로 넘어가면 잘못된 예측을 올리게 된다).
    resp.raise_for_status()

    df = pd.DataFrame(resp.json())
    # "2026-10-29T04:00:00Z" 문자열 -> 시간대(UTC)가 있는 시각 타입으로 변환
    df["candle_time"] = pd.to_datetime(df["candle_time"], utc=True)
    return df


def post_forecast(forecast: dict) -> bool:
    """예측 결과 한 건을 백엔드에 올린다.
    forecast: forecaster.make_forecasts()가 만든 dict 한 개
    돌려주는 값: True면 새로 저장됨, False면 같은 예측(같은 코인, 기간, 기준 시각)이 이미 있어서 건너뜀.
    """

    # json=forecast: dict를 JSON으로 바꿔서 요청 본문에 담는다
    resp = httpx.post(
        f"{settings.backend_url}/api/internal/forecasts",
        json=forecast,
        headers={"X-API-Key": settings.internal_api_key},
        timeout=10,
    )
    # 4xx, 5xx면 예외를 던진다. 422는 백엔드 입력 검사에서 막힌 것 (숫자 범위, 순서 등)
    resp.raise_for_status()
    return resp.json()["saved"]
