import numpy as np
import pytest

from forecaster import model_label, summarize

# 1, 2, ..., 100 처럼 값을 알고 있는 입력으로 summarize의 결과를 손으로 계산해 비교한다.
CLOSES = np.arange(1, 101, dtype=float)


def test_범위는_안쪽에서_바깥쪽_순서다():
    # 백엔드(ForecastCreate)가 이 순서를 검사해서 어긋나면 422로 거절한다.
    # 업로드 전에 여기서 먼저 보장한다.
    r = summarize(np.random.default_rng(0).normal(100, 5, 300), base_price=100)

    assert r["low_80"] <= r["low_50"] <= r["median"] <= r["high_50"] <= r["high_80"]


def test_알려진_입력의_중앙값과_범위():
    r = summarize(CLOSES, base_price=50)

    # numpy.percentile은 값 사이를 직선으로 이어서 계산한다 (1~100의 50%는 50.5).
    assert r["median"] == pytest.approx(50.5)
    assert r["low_50"] == pytest.approx(25.75)
    assert r["high_50"] == pytest.approx(75.25)
    assert r["low_80"] == pytest.approx(10.9)
    assert r["high_80"] == pytest.approx(90.1)


def test_상승_확률은_기준가보다_높은_비율이다():
    # 51~100이 50보다 크므로 50개 / 100개 = 0.5
    assert summarize(CLOSES, base_price=50)["up_probability"] == 0.5


def test_전부_높거나_낮으면_확률은_1_또는_0():
    assert summarize(CLOSES, base_price=0)["up_probability"] == 1.0
    assert summarize(CLOSES, base_price=1000)["up_probability"] == 0.0


def test_기준가와_같은_값은_오른_것으로_세지_않는다():
    # 50과 같은 값은 '높게'가 아니므로 제외된다 (>, 초과). 51~100만 센다.
    assert summarize(CLOSES, base_price=50)["up_probability"] == 0.5
    assert summarize(np.full(10, 50.0), base_price=50)["up_probability"] == 0.0


def test_값은_파이썬_float이다():
    # numpy 숫자 타입이 섞이면 JSON으로 바꿀 때 실패할 수 있어서 float로 바꿔 둔다.
    r = summarize(CLOSES, base_price=50)

    assert all(type(v) is float for v in r.values())


def test_이름표는_입력_봉마다_다르다():
    assert model_label("4h") != model_label("1d")
    assert model_label("4h").endswith("|4h42")
    assert model_label("1d").endswith("|1d7")
