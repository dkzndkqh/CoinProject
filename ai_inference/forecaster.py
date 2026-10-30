import numpy as np
import pandas as pd

from config import INPUTS, settings
from kronos_model import Kronos, KronosPredictor, KronosTokenizer

# 봉 하나의 길이. pandas의 freq 문자열("1d" 등)은 버전마다 해석이 달라질 수 있어서
# Timedelta(자바의 Duration과 같은 "시간 길이" 타입)로 직접 정의한다.
STEP = {
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}

# Kronos에 넣는 컬럼. amount(거래대금)는 넣지 않으면 Kronos가 volume x 평균가로 알아서 만든다.
PRICE_COLS = ["open", "high", "low", "close", "volume"]


def load_predictor() -> KronosPredictor:
    """모델과 토크나이저를 불러와 GPU에 올린다. 무거운 작업이라 프로그램 시작 때 한 번만 호출한다.
    모델 이름은 .env(config)에서 오므로 다른 버전 모델로 바꿀 때 코드를 고치지 않는다.
    첫 실행 때만 HuggingFace에서 가중치를 내려받고 이후에는 캐시를 쓴다.
    """
    tokenizer = KronosTokenizer.from_pretrained(settings.kronos_tokenizer)
    model = Kronos.from_pretrained(settings.kronos_model)
    # device를 안 주면 Kronos가 GPU(cuda)를 자동으로 찾는다.
    return KronosPredictor(model, tokenizer, max_context=512)


def sample_paths(
    predictor: KronosPredictor,
    candles: pd.DataFrame,
    timeframe: str,
    n: int,
) -> np.ndarray:
    """모델에게 앞으로의 가격을 n번 물어보고, 매번 '모든 칸의 종가'를 모아서 돌려준다.

    돌려주는 표는 n줄 x 42칸이다. 한 줄이 '한 번 물어본 답 하나'(4시간 뒤부터 7일 뒤까지의 종가)다.
    예전에는 마지막 칸만 꺼냈는데, 중간 칸(2일 뒤 등)도 쓰려고 전부 가져온다.
    """

    pred_len = INPUTS[timeframe]["pred_len"]  # 이 입력이 예측할 칸 수
    step = STEP[timeframe]

    # 받아온 캔들 각각의 시작 시각 목록 (UTC 표시만 뗀다)
    x_ts = candles["candle_time"].dt.tz_localize(None)
    last = x_ts.iloc[-1]  # 마지막 캔들의 시작 시각

    # 앞으로 맞힐 42칸의 시작 시각 목록 (마지막 캔들 바로 다음 칸부터)
    y_ts = pd.Series([last + step * (i + 1) for i in range(pred_len)])

    df = candles[PRICE_COLS]

    paths = []  # 물어본 답들을 여기에 모은다
    for _ in range(n):
        pred = predictor.predict(
            df,
            x_ts,
            y_ts,
            pred_len=pred_len,
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
        # 답 하나 = 42칸의 종가 (길이 42짜리 배열)
        paths.append(pred["close"].to_numpy())
    return np.array(paths)  # 모양: (n, 42)


def summarize(closes: np.ndarray, base_price: float) -> dict:
    """모아 둔 가격들로 '범위'와 '오를 확률'을 계산한다.

    closes: 300번 물어보고 모은 한 기간(칸)의 종가들
    base_price: 지금 가격 (이 가격보다 높게 나온 답이 몇 개인지 센다)
    """

    # 가격들을 작은 순서로 줄 세웠을 때 10%, 25%, 50%, 75%, 90% 위치에 있는 값을 꺼낸다.
    # 300개라면 30번째, 75번째, 150번째, 225번째, 270번째 값이다.
    #   10%~90% 사이 = "80% 확률로 이 범위 안"
    #   25%~75% 사이 = "50% 확률로 이 범위 안"
    #   50% 위치 = 중앙값
    low_80, low_50, median, high_50, high_80 = np.percentile(
        closes, [10, 25, 50, 75, 90]
    )
    return {
        "median": float(median),
        "low_50": float(low_50),
        "high_50": float(high_50),
        "low_80": float(low_80),
        "high_80": float(high_80),
        # (closes > base_price)는 가격마다 "지금보다 높은가?"를 True/False로 적은 목록이다.
        # 여기에 평균(.mean())을 내면 True가 차지하는 비율이 나온다. 이게 오를 확률이다.
        # 자바 스트림으로 쓰면 filter(x -> x > base).count() / n 이다.
        "up_probability": float((closes > base_price).mean()),
    }


def make_forecasts(
    predictor: KronosPredictor, market: str, timeframe: str, candles: pd.DataFrame
) -> list[dict]:
    """코인 하나의 예측을 만든다. 한 번 계산해서 SAVE_STEPS의 모든 기간 결과를 돌려준다.

    돌려주는 목록의 한 항목이 백엔드에 올릴 JSON 한 건과 같은 모양이다 (ForecastCreate).
    """
    cfg = INPUTS[timeframe]

    # 기준 가격: 가장 최근에 마감된 캔들의 종가
    base_price = float(candles["close"].iloc[-1])

    # 기준 시각: 가장 최근 캔들이 '끝난' 시각 (시작 시각 + 봉 길이).
    # 예: 08:00에 시작한 4시간봉이면 12:00. 모든 기간이 이 시각을 같이 쓴다.
    base_time = candles["candle_time"].iloc[-1] + STEP[timeframe]

    # 모델에게 settings.sample_count(300)번 물어본다. 이 계산이 가장 오래 걸린다 (코인당 약 3분).
    paths = sample_paths(predictor, candles, timeframe, settings.sample_count)

    results = []
    for horizon, step_no in cfg["save_steps"].items():
        # 300번의 답 중 이 기간에 해당하는 칸의 종가만 꺼낸다.
        # 칸 번호는 1부터 세지만 배열은 0부터라서 1을 뺀다.
        closes = paths[:, step_no - 1]
        results.append(
            {
                "market": market,
                "horizon": horizon,
                "base_time": base_time.isoformat(),
                "base_price": base_price,
                **summarize(closes, base_price),
                "model_name": f"{settings.kronos_model}|n{settings.sample_count}|{timeframe}{cfg['pred_len']}",
            }
        )
    return results
