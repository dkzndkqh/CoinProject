import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market.models import Candle

# timeframe 이름 -> pandas 시간 간격 문자열.
# reindex로 "빠짐없는 시간 격자"를 만들 때 쓴다.
# 지표는 4h, 1d만 쓰기로 했으므로 둘만 둔다 (1h는 지표에 쓰지 않는다).
FREQ = {"4h": "4h", "1d": "1D"}

# DB에서 캔들 읽고 난 후 데이터프레임에 맞춰서 데이터 가공 후 결측 보정


def load_candles_df(db: Session, market: str, timeframe: str) -> pd.DataFrame:
    """DB에서 캔들을 읽어 pandas DataFrame으로 돌려준다.
    결측(빠진 캔들)은 메모리에서만 채우고, DB에는 가짜 캔들을 넣지 않는다.

    반환 형태: index = candle_time(시간순), 컬럼 = open, high, low, close, volume
    """
    # 1) 조회. SQL의 SELECT * FROM candles WHERE ... ORDER BY candle_time 과 같다.
    #    자바 JPA의 findByMarketAndTimeframeOrderByCandleTime() 정도에 해당한다.
    stmt = (
        select(Candle)
        .where(Candle.market == market, Candle.timeframe == timeframe)
        .order_by(Candle.candle_time)
    )
    candles = db.scalars(stmt).all()  # Candle 객체 리스트 (자바의 List<Candle>)

    # 2) 객체 리스트 -> DataFrame.
    #    DataFrame은 엑셀 표처럼 행/열이 있는 자료구조다.
    #    자바에는 딱 맞는 표준 클래스가 없고, 컬럼 단위 연산이 가능한 List<Row> 정도로 생각하면 된다.
    #    [ {...}, {...} ] 형태의 dict 리스트를 주면 키가 컬럼 이름이 된다.

    df = pd.DataFrame(
        [
            {
                "candle_time": c.candle_time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
    )
    if df.empty:
        return df  # 데이터가 없으면 그대로 돌려준다

    # 3) candle_time을 인덱스(행 이름표)로 쓴다. 시간으로 행을 찾고 정렬하기 위함이다.
    df = df.set_index("candle_time")

    # 4) 빠짐없는 시간 격자를 만든다. 첫 캔들 ~ 마지막 캔들 사이를 4h(또는 1D) 간격으로 전부 나열한다.
    #    예: 00:00, 04:00, 08:00, ... 중에 DB에 없는 시각이 있으면 아래 reindex가 빈 행을 만든다.
    full_index = pd.date_range(
        df.index[0], df.index[-1], freq=FREQ[timeframe], name="candle_time"
    )

    # 5) reindex: 인덱스를 full_index에 맞춘다. 있는 행은 그대로, 없는 시각은 NaN(빈 값) 행이 생긴다.
    df = df.reindex(full_index)

    # 6) 빈 행 채우기. 거래가 없던 시간은 "직전 종가에서 가격이 안 움직였다"고 본다.
    #    close: 앞의 값으로 채운다 (ffill = forward fill)
    df["close"] = df["close"].ffill()
    #    open/high/low: 빈 곳은 방금 채운 close(= 직전 종가)로 채운다
    for col in ("open", "high", "low"):
        df[col] = df[col].fillna(df["close"])
    #    volume: 거래가 없었으므로 0
    df["volume"] = df["volume"].fillna(0)

    return df


# 지표 계산 (RSI, MACD, 볼린저밴드, 이동평균, 거래량)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """캔들 표에 지표 컬럼을 추가해서 돌려준다.
    입력 df는 load_candles_df()의 결과(결측 보정이 끝난 표)다.
    원본을 바꾸지 않으려고 복사본(copy)에 작업한다. 자바의 방어적 복사와 같다.
    """

    df = df.copy()
    close = df["close"]  # 종가 컬럼

    # ---이동평균 (SMA) : 최근 N개의 종가의 평균 ---
    # rolling(20): 맨 아래 20개씩 창(window)를 밀면서 보겠다.
    # 자바로 치면 "i번째부터 뒤로 20개를 잘라 평균을 내는 for문"을 컬럼 전체에 한 번에 돌려주는 것이다.
    # 앞쪽 19개 행은 20개가 안 모여서 NaN이 된다. (정상이다)
    for n in (5, 20, 60, 120, 200):
        df[f"ma{n}"] = close.rolling(n).mean()

    # --- RSI(14): 과매수/과매도 지표 (0~100) ---
    # 1) diff(): 바로 앞 행과의 차이 = 종가 변화량
    delta = close.diff()

    # 2) 오른 날의 상승폭, 내린 날의 하락폭 분리 (clip: 범위 밖 값을 잘라냄)
    gain = delta.clip(lower=0)  # 하락은 0으로
    loss = -delta.clip(upper=0)  # 상승은 0으로, 하락은 양수로 바꿔서

    # 3) 평균 상승폭 / 평균 하락폭. RSI 표준은 Wilder 평활법이라 ewm(alpha=1/14)를 쓴다.
    #    ewm = 지수가중이동평균: 최근 값에 더 큰 가중치를 준다.
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    # 4) RS = 평균상승 / 평균하락, RSI = 100 - 100 / (1 + RS)
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - 100 / (1 + rs)

    # --- MACD (12, 26, 9) ---
    # macd = EMA12 - EMA26 (단기 추세 - 장기 추세)
    # signal = macd의 9일 EMA, hist = macd - signal (막대그래프로 그리는 값)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # --- 볼린저밴드 (20, 2) ---
    # 중심선 = 20 SMA, 상단 = 중심 + 2*표준편차, 하단 = 중심 - 2*표준편차
    # std(ddof=0): 모표준편차. 볼린저밴드 표준 정의가 이쪽이다 (pandas 기본은 ddof=1이라 값이 다르다).
    std20 = close.rolling(20).std(ddof=0)
    df["bb_mid"] = df["ma20"]
    df["bb_upper"] = df["ma20"] + 2 * std20
    df["bb_lower"] = df["ma20"] - 2 * std20

    # --- 거래량: 최근 20개 평균 대비 현재 거래량 비율 ---
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma20"]

    # --- 일목균형표 (9, 26, 52) ---
    # 구름대를 만드는 지표다. 모두 "고가·저가 기준 중간값"으로 계산한다 (종가가 아님).
    # 헬퍼: N개 구간의 (최고가 + 최저가) / 2
    def _mid(n: int) -> pd.Series:
        return (df["high"].rolling(n).max() + df["low"].rolling(n).min()) / 2

    df["tenkan"] = _mid(9)  # 전환선: 단기 중심선
    df["kijun"] = _mid(26)  # 기준선: 중기 중심선

    # 선행스팬은 계산한 값을 "26칸 미래"에 그린다. 그래서 shift(26)을 쓴다.
    # shift(26): 값을 26행 아래로 민다. 즉 t행에는 26개 전에 계산된 값이 들어간다.
    # 결과적으로 "현재 시각 t의 구름" = 26개 전에 계산해둔 선행스팬 값이다.
    # 가격이 구름 위/아래인지 판정할 때는 이 값(t행의 구름)을 현재 종가와 비교하면 된다.
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(26)
    df["senkou_b"] = _mid(52).shift(26)

    # 후행스팬: 현재 종가를 26칸 과거에 그린다. shift(-26)은 위로 민다.
    # 마지막 26행은 NaN이 된다 (미래 종가는 아직 없으므로 정상이다).
    df["chikou"] = df["close"].shift(-26)

    return df


def _missing(*values) -> bool:
    """값 중 하나라도 NaN이면 True. 판정에 쓸 수 없다는 뜻이다.
    pd.isna(): NaN 여부 검사 (자바의 Double.isNaN과 같다). *values는 여러 값을 받는 문법(자바의 가변 인자 Object...)."""
    return any(pd.isna(v) for v in values)


def judge_indicators(df: pd.DataFrame) -> dict:
    """add_indicators()가 만든 표의 마지막 행들을 읽어 '상태'로 판정해 dict로 돌려준다.
    LLM에는 이 dict만 전달한다 (숫자 계산·판정은 코드가 하고 LLM은 해석만 한다).

    기준 행:
    now  = df.iloc[-1]  최신 캔들(진행 중일 수 있음) -> 현재가에만 쓴다
    last = df.iloc[-2]  마감된 직전 캔들 -> 지표 값과 신호 판정에 쓴다
    prev = df.iloc[-3]  그 이전 캔들 -> 크로스(교차) 판정을 위해 필요
    df.iloc[-1]은 '맨 뒤 행' (파이썬은 음수 인덱스가 뒤에서부터 센다. 자바 배열엔 없는 문법).
    """
    now, last, prev = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    price = now["close"]  # 현재가 = 최신 캔들 종가

    # --- RSI: 70 이상 과매수, 30 이하 과매도 (표준 기준) ---
    rsi = last["rsi"]
    if _missing(rsi):
        rsi_state = "데이터 부족"
    elif rsi >= 70:
        rsi_state = "과매수"
    elif rsi <= 30:
        rsi_state = "과매도"
    else:
        rsi_state = "중립"

    # --- MACD: 히스토그램 부호가 바뀐 순간이 크로스 ---
    # hist = macd - signal. 음수 -> 양수면 골든크로스, 양수 -> 음수면 데드크로스.
    if _missing(last["macd_hist"], prev["macd_hist"]):
        macd_state = "데이터 부족"
    elif prev["macd_hist"] < 0 <= last["macd_hist"]:  # 0 <= x 체인 비교는 파이썬 문법
        macd_state = "골든크로스"
    elif prev["macd_hist"] >= 0 > last["macd_hist"]:
        macd_state = "데드크로스"
    elif last["macd_hist"] > 0:
        macd_state = "시그널선 위 (상승 우위)"
    else:
        macd_state = "시그널선 아래 (하락 우위)"

    # --- 볼린저밴드: 현재가가 마감 캔들의 상단/하단 밖에 있는지 ---
    if _missing(last["bb_upper"], last["bb_lower"]):
        bb_state = "데이터 부족"
    elif price > last["bb_upper"]:
        bb_state = "상단 돌파"
    elif price < last["bb_lower"]:
        bb_state = "하단 이탈"
    else:
        bb_state = "밴드 내"

    # --- 이동평균: 배열(5>20>60이면 정배열) + 현재가 vs 200선 ---
    if _missing(last["ma5"], last["ma20"], last["ma60"]):
        ma_state = "데이터 부족"
    elif last["ma5"] > last["ma20"] > last["ma60"]:
        ma_state = "정배열 (상승 추세)"
    elif last["ma5"] < last["ma20"] < last["ma60"]:
        ma_state = "역배열 (하락 추세)"
    else:
        ma_state = "혼조"
    if _missing(last["ma200"]):
        ma200_state = "데이터 부족"
    else:
        ma200_state = "200선 위" if price > last["ma200"] else "200선 아래"

    # --- 거래량: 마감 캔들 기준 20개 평균 대비 비율 (진행 중 캔들은 일부만 쌓여서 쓰지 않는다) ---
    vol = last["vol_ratio"]
    if _missing(vol):
        vol_state = "데이터 부족"
    elif vol >= 1.5:
        vol_state = "급증"
    elif vol <= 0.5:
        vol_state = "감소"
    else:
        vol_state = "보통"

    # --- 일목균형표: 현재가의 구름 위치 + 전환선/기준선 관계 ---
    top = max(last["senkou_a"], last["senkou_b"])  # 구름 상단
    bottom = min(
        last["senkou_a"], last["senkou_b"]
    )  # 구름 하단 (NaN이 섞이면 아래에서 걸러진다)
    if _missing(last["senkou_a"], last["senkou_b"]):
        cloud_state = "데이터 부족"
    elif price > top:
        cloud_state = "구름 위 (강세)"
    elif price < bottom:
        cloud_state = "구름 아래 (약세)"
    else:
        cloud_state = "구름 안 (방향 불명확)"
    if _missing(last["tenkan"], last["kijun"]):
        tk_state = "데이터 부족"
    else:
        tk_state = (
            "전환선이 기준선 위"
            if last["tenkan"] > last["kijun"]
            else "전환선이 기준선 아래"
        )

    return {
        "price": float(price),
        "price_time": df.index[-1].isoformat(),  # 현재가 기준 시각
        "basis_time": df.index[-2].isoformat(),  # 지표 판정에 쓴 마감 캔들 시각
        "rsi": {
            "value": None if _missing(rsi) else round(float(rsi), 1),
            "state": rsi_state,
        },
        "macd": {"state": macd_state},
        "bollinger": {"state": bb_state},
        "moving_average": {"alignment": ma_state, "vs_ma200": ma200_state},
        "volume": {
            "ratio": None if _missing(vol) else round(float(vol), 2),
            "state": vol_state,
        },
        "ichimoku": {"cloud": cloud_state, "tenkan_kijun": tk_state},
    }
