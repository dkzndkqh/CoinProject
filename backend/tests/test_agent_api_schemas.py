import pytest
from pydantic import ValidationError

from app.agent import service as agent_service
from app.agent.schemas import AnalyzeRequest, AnalyzeResponse
from tests.test_agent_scenario import FOUR, ONE, make_data

# 정상 요청 하나. 각 테스트에서 한 칸만 바꿔서 쓴다.
VALID_REQUEST = {"market": "KRW-BTC", "question": "3일 뒤 어때?"}


def test_정상_요청은_통과한다():
    req = AnalyzeRequest.model_validate(VALID_REQUEST)
    assert req.market == "KRW-BTC"
    assert req.question == "3일 뒤 어때?"


@pytest.mark.parametrize("market", ["KRW-SOL", "btc", "KRW-btc", "", "BTC-KRW"])
def test_BTC_ETH_말고는_거절한다(market):
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**VALID_REQUEST, "market": market})


def test_질문_앞뒤_공백은_잘린다():
    req = AnalyzeRequest.model_validate({**VALID_REQUEST, "question": "  어때?  "})
    assert req.question == "어때?"


@pytest.mark.parametrize("question", ["", "   ", "\n\t"])
def test_빈_질문과_공백만_있는_질문은_거절한다(question):
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**VALID_REQUEST, "question": question})


def test_질문은_500자까지만_허용한다():
    # 경계: 500자는 통과, 501자는 거절
    AnalyzeRequest.model_validate({**VALID_REQUEST, "question": "가" * 500})
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({**VALID_REQUEST, "question": "가" * 501})


def test_질문_칸이_없으면_거절한다():
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate({"market": "KRW-BTC"})


def response_dict(scenario):
    """analyze()가 돌려주는 dict와 같은 모양. scenario만 바꿔 끼운다."""
    return {
        "market": "KRW-BTC",
        "stance": "관망",
        "horizon": "3d",
        "message": "지금은 방향이 뚜렷하지 않아 관망을 권합니다.",
        "price": 100000000.0,
        "price_time_kst": "2026-11-02 12:00 KST",
        "scenario": scenario,
        "disclaimer": agent_service.DISCLAIMER,
    }


def test_build_scenario가_만든_값이_응답_양식에_그대로_들어간다():
    # 서비스가 만드는 dict와 응답 양식의 칸 이름·타입이 서로 맞는지 확인한다 (둘이 어긋나면 응답 직전에 터진다).
    scenario = agent_service.build_scenario(make_data(FOUR, ONE), "3d")

    resp = AnalyzeResponse.model_validate(response_dict(scenario))

    assert resp.scenario.input == "1d"
    assert [p.horizon for p in resp.scenario.points] == ["1d", "2d", "3d"]
    assert resp.scenario.points[-1].median == scenario["points"][-1]["median"]


def test_scenario가_None이어도_응답_양식을_통과한다():
    resp = AnalyzeResponse.model_validate(response_dict(None))
    assert resp.scenario is None


def test_응답의_stance도_세_값만_허용한다():
    with pytest.raises(ValidationError):
        AnalyzeResponse.model_validate({**response_dict(None), "stance": "BUY"})
