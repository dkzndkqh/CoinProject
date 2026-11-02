from app.agent import service as agent_service


def forecast(names):
    """build_agent_input이 만드는 예측 한 입력의 모양을 흉내 낸다. names 순서를 일부러 섞어서 정렬도 검사한다."""
    horizons = {}
    for i, name in enumerate(names, start=1):
        horizons[name] = {
            "target_time_kst": f"target-{name}",
            "median": 100.0 + i,
            "median_vs_price_pct": float(i),
            "range_80": [90.0 + i, 110.0 + i],
            "range_80_vs_price_pct": [-10.0 + i, 10.0 + i],
            "up_probability": 0.5,
            "down_probability": 0.5,
        }
    return {
        "base_time_kst": "2026-11-02 13:00 KST",
        "hours_ago": 1.4,
        "base_price": 100.0,
        "horizons": horizons,
    }


def make_data(four, one):
    """four, one: 각 입력이 가진 기간 이름 목록. None이면 그 입력은 아직 예측이 없는 것."""
    return {
        "forecasts": {
            "4h": forecast(four) if four is not None else None,
            "1d": forecast(one) if one is not None else None,
        }
    }


FOUR = ["1d", "4h", "12h", "8h", "2d", "3d", "7d"]  # 일부러 섞은 순서
ONE = ["7d", "1d", "3d", "2d"]


def test_짧은_기간은_4h_입력을_쓰고_질문_기간까지_시간순으로_담는다():
    result = agent_service.build_scenario(make_data(FOUR, ONE), "1d")

    assert result["input"] == "4h"
    assert [p["horizon"] for p in result["points"]] == ["4h", "8h", "12h", "1d"]
    assert result["horizon"] == "1d"
    assert result["base_time_kst"] == "2026-11-02 13:00 KST"
    assert result["hours_ago"] == 1.4


def test_긴_기간은_일봉_입력을_쓴다():
    result = agent_service.build_scenario(make_data(FOUR, ONE), "3d")

    assert result["input"] == "1d"
    assert [p["horizon"] for p in result["points"]] == ["1d", "2d", "3d"]


def test_2일이_경계다_12시간은_4h_2일은_일봉():
    data = make_data(FOUR, ONE)
    assert agent_service.build_scenario(data, "12h")["input"] == "4h"
    assert agent_service.build_scenario(data, "2d")["input"] == "1d"


def test_값은_계산하지_않고_그대로_옮긴다():
    result = agent_service.build_scenario(make_data(["4h"], None), "4h")

    point = result["points"][0]
    assert point["median"] == 101.0
    assert point["low_80"] == 91.0
    assert point["high_80"] == 111.0
    assert point["median_vs_price_pct"] == 1.0
    assert point["low_80_vs_price_pct"] == -9.0
    assert point["high_80_vs_price_pct"] == 11.0
    assert point["target_time_kst"] == "target-4h"


def test_마지막_점이_질문한_기간이다():
    result = agent_service.build_scenario(make_data(FOUR, ONE), "7d")

    assert result["points"][-1]["horizon"] == "7d"


def test_기본_입력이_없으면_다른_입력으로_대신한다():
    # 7d는 일봉 입력이 기본인데 일봉 예측이 아직 없다 -> 4h 입력으로 대신한다
    result = agent_service.build_scenario(make_data(FOUR, None), "7d")

    assert result["input"] == "4h"
    assert result["points"][-1]["horizon"] == "7d"


def test_쓸_예측이_없으면_None():
    # 예측이 둘 다 없다
    assert agent_service.build_scenario(make_data(None, None), "1d") is None
    # 예측은 있지만 그 기간(5d)이 어느 입력에도 없다
    assert agent_service.build_scenario(make_data(FOUR, ONE), "5d") is None
