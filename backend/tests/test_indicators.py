from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from app.market.indicators import add_indicators, judge_indicators, load_candles_df

# float("nan"): NaN(숫자가 아님, 값이 없음)을 만든다. 자바의 Double.NaN과 같다.
# 지표 계산 초반처럼 "데이터가 모자란 칸"을 흉내 낼 때 쓴다.
NAN = float("nan")


# ─────────────── 가짜 DB와 데이터 만들기 도구 ───────────────


class FakeDB:
    """load_candles_df가 db.scalars(stmt).all() 만 쓰므로, 그 모양만 흉내 낸 가짜 세션.
    진짜 DB 없이 테스트하려는 것이다. 자바의 Mockito mock이나 손으로 만든 Stub 클래스와 같은 역할이다.
    """

    def __init__(self, candles):
        self._candles = candles  # 앞의 _ 는 "내부용"이라는 관례다 (자바의 private 느낌, 강제는 아님)

    def scalars(self, stmt):
        # stmt(쿼리)는 무시하고 미리 넣어둔 캔들을 돌려준다.
        # SimpleNamespace(all=함수): "all()을 호출할 수 있는 객체"를 한 줄로 만든다.
        # lambda: ... 는 이름 없는 함수다 (자바의 람다 () -> ... 와 같다).
        return SimpleNamespace(all=lambda: self._candles)


def make_candle(hour, close, volume=5.0):
    """Candle 모델 대신 쓰는 가짜 캔들. 시/고/저/종가를 같은 값으로 둬서 단순하게 만든다.
    SimpleNamespace는 필드만 있는 임시 객체다 (자바의 간단한 DTO/record와 비슷)."""
    return SimpleNamespace(
        candle_time=datetime(2025, 1, 1, hour, tzinfo=UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
    )


def make_close_df(closes):
    """종가 목록만 주면 4시간 간격 캔들 표(DataFrame)를 만든다. add_indicators 입력용.
    시/고/저/종가를 모두 같은 값으로 둬서 종가 기반 지표(RSI, 볼린저)를 손계산하기 쉽게 한다."""
    index = pd.date_range(
        "2025-01-01", periods=len(closes), freq="4h", tz="UTC", name="candle_time"
    )
    s = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame({"open": s, "high": s, "low": s, "close": s, "volume": 1.0})


# ─────────────── load_candles_df: 결측 보정 ───────────────


def test_결측_캔들은_직전_종가와_거래량_0으로_채워진다():
    """00:00, 04:00, 12:00만 있고 08:00이 빠진 가짜 데이터.
    기대: 08:00 행이 새로 생기고, 값은 직전 종가(110)로, 거래량은 0으로 채워진다."""
    db = FakeDB([make_candle(0, 100.0), make_candle(4, 110.0), make_candle(12, 130.0)])

    df = load_candles_df(db, "KRW-BTC", "4h")

    assert len(df) == 4  # 3개 -> 빈 칸이 채워져 4개
    missing = df.iloc[2]  # iloc[2] = 위에서 세 번째 행 (인덱스는 0부터)
    assert df.index[2].hour == 8  # 새로 생긴 행이 08:00인지
    assert missing["close"] == 110.0  # 직전 종가로 채움
    assert missing["open"] == missing["high"] == missing["low"] == 110.0
    assert missing["volume"] == 0  # 거래 없음
    assert df.iloc[3]["close"] == 130.0  # 뒤의 진짜 캔들은 그대로


def test_캔들이_없으면_빈_표를_돌려준다():
    assert load_candles_df(FakeDB([]), "KRW-BTC", "4h").empty


# ─────────────── add_indicators: 손계산 값과 비교 ───────────────


def test_RSI_손계산_값():
    """종가 100 -> 110 -> 100.
    평균상승 = 10 * 13/14, 평균하락 = 10/14 (alpha = 1/14로 평활), RS = 13, RSI = 100 - 100/14.
    pytest.approx: 소수점 오차를 허용하는 비교 (자바 JUnit의 assertEquals(expected, actual, delta))."""
    df = add_indicators(make_close_df([100, 110, 100]))
    assert df["rsi"].iloc[-1] == pytest.approx(100 - 100 / 14)


def test_계속_오르기만_하면_RSI는_100():
    """하락이 하나도 없으면 평균하락이 0이라 RS가 무한대가 되고 RSI는 100이 된다.
    0으로 나누기가 에러가 되지 않고 100으로 나오는지 확인한다."""
    df = add_indicators(make_close_df(range(100, 130)))
    assert df["rsi"].iloc[-1] == pytest.approx(100.0)


def test_볼린저밴드_손계산_값():
    """종가 1~20. 평균 10.5, 모표준편차(ddof=0) = sqrt(33.25).
    표본표준편차(ddof=1)로 잘못 계산하면 값이 달라지므로 ddof=0 설정을 지켜주는 테스트이기도 하다."""
    df = add_indicators(make_close_df(range(1, 21)))
    last = df.iloc[-1]
    assert last["bb_mid"] == pytest.approx(10.5)
    assert last["bb_upper"] == pytest.approx(10.5 + 2 * 33.25**0.5)
    assert last["bb_lower"] == pytest.approx(10.5 - 2 * 33.25**0.5)


def test_add_indicators는_원본을_바꾸지_않는다():
    df = make_close_df(range(1, 31))
    add_indicators(df)
    assert "rsi" not in df.columns  # 복사본에만 지표가 붙었는지


# ─────────────── judge_indicators: 판정 경계값 ───────────────

# 기본 행: 모든 지표가 "중립/정상" 판정이 나오는 값. 테스트마다 바꿀 칸만 덮어쓴다.
BASE = {
    "close": 100.0,
    "rsi": 50.0,
    "macd_hist": 1.0,
    "bb_upper": 110.0,
    "bb_lower": 90.0,
    "ma5": 120.0,
    "ma20": 110.0,
    "ma60": 100.0,
    "ma200": 90.0,
    "vol_ratio": 1.0,
    "senkou_a": 95.0,
    "senkou_b": 90.0,
    "tenkan": 101.0,
    "kijun": 100.0,
}


def make_judge_df(prev=None, last=None, now=None):
    """judge_indicators가 읽는 3개 행(iloc[-3]=prev, [-2]=last 마감 캔들, [-1]=now 최신)으로 된 표.
    {**BASE, **덮어쓸값}: dict 두 개를 합치고 뒤의 것이 이긴다 (파이썬의 dict 병합 문법).
    `prev or {}`: prev가 None이면 빈 dict를 쓴다."""
    rows = [{**BASE, **(prev or {})}, {**BASE, **(last or {})}, {**BASE, **(now or {})}]
    index = pd.date_range("2025-01-01", periods=3, freq="4h", tz="UTC")
    return pd.DataFrame(rows, index=index)


# parametrize: 같은 테스트를 입력값만 바꿔 여러 번 실행한다 (JUnit @ParameterizedTest + @CsvSource).
@pytest.mark.parametrize(
    "rsi, expected",
    [
        (70, "과매수"),
        (69.9, "중립"),
        (30, "과매도"),
        (30.1, "중립"),
        (NAN, "데이터 부족"),
    ],
)
def test_RSI_판정_경계값(rsi, expected):
    result = judge_indicators(make_judge_df(last={"rsi": rsi}))
    assert result["rsi"]["state"] == expected


@pytest.mark.parametrize(
    "ratio, expected",
    [
        (1.5, "급증"),
        (1.49, "보통"),
        (0.5, "감소"),
        (0.51, "보통"),
        (NAN, "데이터 부족"),
    ],
)
def test_거래량_판정_경계값(ratio, expected):
    result = judge_indicators(make_judge_df(last={"vol_ratio": ratio}))
    assert result["volume"]["state"] == expected


@pytest.mark.parametrize(
    "prev_hist, last_hist, expected",
    [
        (-1.0, 0.0, "골든크로스"),  # 경계: 0이 되는 순간도 크로스로 본다 (0 <= x)
        (-1.0, 1.0, "골든크로스"),
        (0.0, -1.0, "데드크로스"),
        (1.0, 2.0, "시그널선 위 (상승 우위)"),
        (-2.0, -1.0, "시그널선 아래 (하락 우위)"),
        (NAN, 1.0, "데이터 부족"),
    ],
)
def test_MACD_크로스_판정(prev_hist, last_hist, expected):
    result = judge_indicators(
        make_judge_df(prev={"macd_hist": prev_hist}, last={"macd_hist": last_hist})
    )
    assert result["macd"]["state"] == expected


@pytest.mark.parametrize(
    "price, expected",
    [(110.1, "상단 돌파"), (110.0, "밴드 내"), (90.0, "밴드 내"), (89.9, "하단 이탈")],
)
def test_볼린저_판정은_현재가로_한다(price, expected):
    # 현재가는 now(최신 캔들)의 close, 밴드는 last(마감 캔들)의 값이다.
    result = judge_indicators(make_judge_df(now={"close": price}))
    assert result["bollinger"]["state"] == expected


@pytest.mark.parametrize(
    "price, expected",
    [
        (96.0, "구름 위 (강세)"),
        (95.0, "구름 안 (방향 불명확)"),  # 경계: 상단과 같으면 "안"
        (90.0, "구름 안 (방향 불명확)"),  # 경계: 하단과 같으면 "안"
        (89.0, "구름 아래 (약세)"),
    ],
)
def test_구름_판정(price, expected):
    result = judge_indicators(make_judge_df(now={"close": price}))
    assert result["ichimoku"]["cloud"] == expected


def test_구름이_NaN이면_데이터_부족():
    result = judge_indicators(make_judge_df(last={"senkou_a": NAN}))
    assert result["ichimoku"]["cloud"] == "데이터 부족"


def test_이동평균_배열_판정():
    assert (
        judge_indicators(make_judge_df())["moving_average"]["alignment"]
        == "정배열 (상승 추세)"
    )
    reverse = judge_indicators(
        make_judge_df(last={"ma5": 90.0, "ma20": 95.0, "ma60": 100.0})
    )
    assert reverse["moving_average"]["alignment"] == "역배열 (하락 추세)"
    mixed = judge_indicators(
        make_judge_df(last={"ma5": 100.0, "ma20": 110.0, "ma60": 105.0})
    )
    assert mixed["moving_average"]["alignment"] == "혼조"


def test_신호는_마감_캔들_현재가는_최신_캔들에서_읽는다():
    """핵심 규칙 검증: 최신 캔들(now)의 RSI가 99(과매수)여도 판정은 마감 캔들(last, RSI 50)로 해야 한다.
    현재가와 price_time은 최신 캔들, basis_time은 마감 캔들의 시각이어야 한다."""
    df = make_judge_df(last={"rsi": 50.0}, now={"rsi": 99.0, "close": 123.0})

    result = judge_indicators(df)

    assert result["rsi"]["state"] == "중립"
    assert result["price"] == 123.0
    assert result["price_time"] == df.index[-1].isoformat()
    assert result["basis_time"] == df.index[-2].isoformat()


def test_캔들이_부족하면_장기_지표는_데이터_부족():
    """30개 캔들로는 ma60, ma200, 일목 구름(52+26개 필요)을 못 만든다.
    에러 없이 "데이터 부족"으로 나와야 LLM이 추측하지 않는다."""
    df = add_indicators(make_close_df(range(100, 130)))

    result = judge_indicators(df)

    assert result["moving_average"]["vs_ma200"] == "데이터 부족"
    assert result["moving_average"]["alignment"] == "데이터 부족"
    assert result["ichimoku"]["cloud"] == "데이터 부족"
