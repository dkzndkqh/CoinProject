import pytest
from pydantic import ValidationError

from app.agent.schemas import AnalysisResult

# 정상 값 하나. 각 테스트에서 한 칸만 바꿔서 쓴다.
VALID = {
    "stance": "관망",
    "horizon": "1d",
    "message": "지금은 방향이 뚜렷하지 않아 관망을 권합니다.",
}


def test_정상_응답은_통과한다():
    result = AnalysisResult.model_validate(VALID)
    assert result.stance == "관망"
    assert result.horizon == "1d"


@pytest.mark.parametrize("stance", ["BUY", "매수 추천", "", "hold"])
def test_허용되지_않는_stance는_거절한다(stance):
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({**VALID, "stance": stance})


@pytest.mark.parametrize("horizon", ["2일", "1w", "d", "7", "1 d", ""])
def test_형식이_다른_horizon은_거절한다(horizon):
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({**VALID, "horizon": horizon})


def test_짧은_message와_빈_message는_거절한다():
    for message in ["", "짧음"]:
        with pytest.raises(ValidationError):
            AnalysisResult.model_validate({**VALID, "message": message})


def test_칸이_빠지면_거절한다():
    # {**VALID, ...} 문법: VALID의 내용을 펼친 뒤 일부를 덮어쓴다.
    # 아래는 stance 칸만 뺀 딕셔너리를 만든다.
    without_stance = {k: v for k, v in VALID.items() if k != "stance"}
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(without_stance)


def test_json_스키마에_세_칸이_모두_필수로_들어간다():
    # Claude에게 줄 도구 정의의 재료가 제대로 나오는지 확인한다.
    schema = AnalysisResult.model_json_schema()
    assert set(schema["required"]) == {"stance", "horizon", "message"}
    assert schema["properties"]["stance"]["enum"] == ["매수", "매도", "관망"]
