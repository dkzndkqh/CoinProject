from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.clients import llm
from app.core.config import settings

TOOL = {
    "name": "submit_analysis",
    "description": "분석 결과를 제출한다",
    "input_schema": {"type": "object", "properties": {}},
}


def fake_client(blocks, stop_reason="tool_use", calls=None):
    """messages.create를 흉내 내는 가짜 클라이언트를 만든다.
    자바 테스트에서 Mockito로 클라이언트를 stub하는 것과 같다.
    SimpleNamespace는 속성만 가진 간단한 가짜 객체다(자바의 익명 객체에 가깝다).
    """

    def create(**kwargs):
        if calls is not None:
            calls.append(kwargs)  # 어떤 인자로 불렀는지 나중에 확인하려고 기록
        return SimpleNamespace(
            content=blocks,
            stop_reason=stop_reason,
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )

    return SimpleNamespace(messages=SimpleNamespace(create=create))


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    # 모든 테스트에서 키가 있는 것처럼 만든다. (CI에는 키가 없다)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")


def test_도구_입력값을_꺼내고_도구_호출을_강제한다(monkeypatch):
    calls = []
    block = SimpleNamespace(
        type="tool_use", name="submit_analysis", input={"stance": "관망"}
    )
    monkeypatch.setattr(llm, "_client", fake_client([block], calls=calls))

    result = llm.ask_with_tool("규칙", "질문", TOOL)

    assert result["input"] == {"stance": "관망"}
    assert result["stop_reason"] == "tool_use"
    assert result["input_tokens"] == 100
    # 도구를 알려주고, 그 도구를 강제로 호출하게 했는지 확인
    assert calls[0]["tools"] == [TOOL]
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "submit_analysis"}


def test_도구_호출이_없으면_input은_None이다(monkeypatch):
    text_block = SimpleNamespace(type="text", text="그냥 글로 답함")
    monkeypatch.setattr(llm, "_client", fake_client([text_block], "end_turn"))

    result = llm.ask_with_tool("규칙", "질문", TOOL)

    assert result["input"] is None
    assert result["stop_reason"] == "end_turn"


def test_키가_없으면_RuntimeError(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(RuntimeError):
        llm.ask_with_tool("규칙", "질문", TOOL)


def test_API_호출이_실패하면_LLMError로_바꾼다(monkeypatch):
    # SDK가 던지는 anthropic.APIError 계열을 우리 에러(LLMError)로 바꾸는지 확인한다.
    def boom(**kwargs):
        raise anthropic.APIConnectionError(
            request=httpx.Request("POST", "https://example.com")
        )

    fake = SimpleNamespace(messages=SimpleNamespace(create=boom))
    monkeypatch.setattr(llm, "_client", fake)

    with pytest.raises(llm.LLMError):
        llm.ask_with_tool("규칙", "질문", TOOL)


# ---- ask_with_tools: 대화를 이어 가며 도구 여러 개를 쓰는 호출 ----

NEWS_TOOL = {
    "name": "get_news",
    "description": "뉴스 기사를 조회한다",
    "input_schema": {"type": "object", "properties": {}},
}


def test_ask_with_tools_도구_요청을_id와_함께_목록으로_돌려준다(monkeypatch):
    # Claude가 도구를 두 개 한꺼번에 요청한 경우. id는 나중에 결과를 맞춰 돌려줄 때 필요하다.
    blocks = [
        SimpleNamespace(type="text", text="기사를 볼게요"),
        SimpleNamespace(type="tool_use", id="t1", name="get_news", input={"days": 7}),
        SimpleNamespace(type="tool_use", id="t2", name="get_news", input={"days": 30}),
    ]
    monkeypatch.setattr(llm, "_client", fake_client(blocks))

    result = llm.ask_with_tools(
        "규칙", [{"role": "user", "content": "질문"}], [NEWS_TOOL]
    )

    assert result["tool_uses"] == [
        {"id": "t1", "name": "get_news", "input": {"days": 7}},
        {"id": "t2", "name": "get_news", "input": {"days": 30}},
    ]
    assert result["content"] == blocks  # 다음 호출에 assistant 메시지로 붙일 원본
    assert result["stop_reason"] == "tool_use"
    assert result["input_tokens"] == 100


def test_ask_with_tools_도구_요청이_없으면_빈_목록이다(monkeypatch):
    text_block = SimpleNamespace(type="text", text="그냥 글로 답함")
    monkeypatch.setattr(llm, "_client", fake_client([text_block], "end_turn"))

    result = llm.ask_with_tools(
        "규칙", [{"role": "user", "content": "질문"}], [NEWS_TOOL]
    )

    assert result["tool_uses"] == []


def test_ask_with_tools_force_tool이_없으면_auto다(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_client", fake_client([], "end_turn", calls=calls))
    messages = [{"role": "user", "content": "질문"}]

    llm.ask_with_tools("규칙", messages, [NEWS_TOOL, TOOL])

    # 도구 목록과 대화 전체를 그대로 보내고, 도구 선택은 Claude에게 맡긴다
    assert calls[0]["tools"] == [NEWS_TOOL, TOOL]
    assert calls[0]["messages"] == messages
    assert calls[0]["tool_choice"] == {"type": "auto"}


def test_ask_with_tools_force_tool이_있으면_그_도구를_강제한다(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_client", fake_client([], "end_turn", calls=calls))

    llm.ask_with_tools(
        "규칙",
        [{"role": "user", "content": "질문"}],
        [NEWS_TOOL, TOOL],
        force_tool="submit_analysis",
    )

    assert calls[0]["tool_choice"] == {"type": "tool", "name": "submit_analysis"}


def test_ask_with_tools_API_호출이_실패하면_LLMError로_바꾼다(monkeypatch):
    def boom(**kwargs):
        raise anthropic.APIConnectionError(
            request=httpx.Request("POST", "https://example.com")
        )

    monkeypatch.setattr(
        llm, "_client", SimpleNamespace(messages=SimpleNamespace(create=boom))
    )

    with pytest.raises(llm.LLMError):
        llm.ask_with_tools("규칙", [{"role": "user", "content": "질문"}], [NEWS_TOOL])


def test_ask_with_tools_키가_없으면_RuntimeError(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(RuntimeError):
        llm.ask_with_tools("규칙", [{"role": "user", "content": "질문"}], [NEWS_TOOL])
