import time

import numpy as np
import pandas as pd
import torch

# 복사해 온 Kronos 코드. 폴더가 패키지라서(__init__.py) 자바의 import처럼 가져온다.
from kronos_model import Kronos, KronosPredictor, KronosTokenizer

LOOKBACK = 512 # 입력 캔들 수(모델 한도 512)
PRED_LEN = 6 # 예측할 캔들 수(4H봉이면 24시간)

# 1) 모델 로드: 처음 실행 할때만 HuggingFace에서 가중치를 내려받는다(캐시됨)
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
predictor = KronosPredictor(model, tokenizer, device="cuda:0", max_context=512)

# 2) 가짜 4시간봉 데이터: 랜덤워크로 종가를 만들고 open/high/low/volume을 덧붙인다.
rng = np.random.default_rng(0)
close = 100_100_000 + np.cumsum(rng.normal(0, 300_000, LOOKBACK))
df  = pd.DataFrame({
    "open": close + rng.normal(0, 100_000, LOOKBACK),
    "high": close  + 500_000,
    "low": close - 500_000,
    "close": close,
    "volume": rng.uniform(10, 100, LOOKBACK),
})

# 시각은 pandas Series여야 한다(내부에서 .dt를 쓴다).
x_ts = pd.Series(pd.date_range("2026-08-01", periods=LOOKBACK, freq="4h"))
y_ts = pd.Series(pd.date_range(x_ts.iloc[-1] + pd.Timedelta(hours=4), periods=PRED_LEN, freq="4h"))

def run(n_calls):
    """sample_count=1로 n_calls번 호출하고 걸린 시간(초)을 돌려준다."""
    torch.cuda.synchronize()  # GPU 작업이 끝날 때까지 기다려야 시간이 정확하다
    t = time.time()
    for _ in range(n_calls):
        predictor.predict(df, x_ts, y_ts, pred_len=PRED_LEN, T=1.0, top_p=0.9,
                        sample_count=1, verbose=False)
    torch.cuda.synchronize()
    return time.time() - t

run(1)  # 워밍업(첫 호출은 느리므로 측정에서 제외)
print(f"1회 호출: {run(1):.2f}초")
print(f"10회 호출: {run(10):.2f}초")
print(f"GPU 최대 메모리: {torch.cuda.max_memory_allocated() / 1024**2:.0f} MB")
