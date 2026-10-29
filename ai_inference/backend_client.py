import httpx
import pandas as pd

from config import settings

def get_candles(market: str, timeframe: str, limit: int =512) -> pd.DataFrame:
    """백엔드 DB의 마감 캔들을 받아 DataFrame으로 돌려준다 (오래된 순).
    Kronos 입력으로 쓰려고 candle_time을 UTC 시각 컬럼으로 바꿔 둔다.
    """
    # httpx.get: 자바의 RestClient.get()과 같다. params는 쿼리스트링(?market=...&limit=...)이 된다.
    # X-API-Key 헤더로 인증한다. 백엔드가 이 키를 .env 값과 비교한다.
    resp = httpx.get(
        f"{settings.backend_url}/api/internal/candles",
        params={"market": market, "timeframe": timeframe, "limit": limit},
        headers={"X-API-Key": settings.internal_api_key},
        timeout=10,
    )
    # 4xx, 5xx면 예외를 던진다 (조용히 빈 데이터로 넘어가면 잘못된 예측을 올리게 된다).
    resp.raise_for_status()

    df = pd.DataFrame(resp.json())
    # "2026-10-29T04:00:00Z" 문자열 -> 시간대(UTC)가 있는 시각 타입으로 변환
    df["candle_time"] = pd.to_datetime(df["candle_time"], utc=True)
    return df