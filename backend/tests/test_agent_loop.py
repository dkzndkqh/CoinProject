from datetime import UTC, datetime

import pytest

from app.agent import service as agent_service
from app.clients import llm
from app.news import service as news_service
from tests.test_agent_analyze import FAKE_DATA, GOOD, raw, req, set_plan

ARTICLE = {
    "published_at": datetime(2026, 11, 11, 3, 0, tzinfo=UTC),
    "source": "coindesk",
    "title": "대형 거래소 해킹",
    "summary": "요약",
    "label": "negative",
    "score": -0.97,
}


def news_request(tool_id="n1", **tool_input):
    """Claude가 get_news를 요청한 응답. 뉴스를 먼저 찾아보고 싶다는 뜻이다."""
    return {
        "content": ["(assistant 응답 블록)"],
        "tool_uses": [{"id": tool_id, "name": "get_news", "input": tool_input}],
        "stop_reason": "tool_use",
        "input_tokens": 100,
        "output_tokens": 50,
    }


@pytest.fixture
def loop(monkeypatch):
    """분류, 데이터 조립, 뉴스 조회, Claude 호출을 가짜로 바꾼다.
    돌려주는 값: (calls, responses, searched)
      calls: Claude를 부를 때마다 {"messages", "tools", "force_tool"}이 쌓이는 목록
      responses: 호출될 때마다 맨 앞에서 하나씩 꺼내 주는 가짜 응답 목록
      searched: DB 뉴스 조회가 받은 (days, limit, sort) 목록
    """
    calls, responses, searched = [], [], []

    def fake_ask(system, messages, tools, force_tool=None, **kwargs):
        # messages는 호출 뒤에도 계속 늘어나는 같은 목록이라, 이 시점의 모습을 복사해 둔다.
        calls.append(
            {"messages": list(messages), "tools": tools, "force_tool": force_tool}
        )
        return responses.pop(0)

    def fake_articles(db, days, limit, sort):
        searched.append((days, limit, sort))
        return [ARTICLE]

    monkeypatch.setattr(agent_service, "build_agent_input", lambda db, m: FAKE_DATA)
    monkeypatch.setattr(llm, "ask_with_tools", fake_ask)
    monkeypatch.setattr(news_service, "get_articles", fake_articles)
    set_plan(monkeypatch)
    return calls, responses, searched


def tool_results(call):
    """한 번의 Claude 호출에 실려 간 마지막 메시지(도구 결과 묶음)를 꺼낸다."""
    last = call["messages"][-1]
    assert last["role"] == "user"
    return last["content"]


def test_뉴스를_요청하면_조회해서_결과를_붙이고_다시_부른다(loop):
    calls, responses, searched = loop
    responses += [news_request(days=7, sort="impact"), raw(GOOD)]

    result = agent_service.analyze(None, req())

    assert result["stance"] == "관망"
    assert len(calls) == 2
    assert searched == [(7, 5, "impact")]  # Claude가 준 값 + 빠진 칸은 기본값
    # 두 번째 호출의 대화: 질문 -> Claude의 요청 -> 도구 결과
    second = calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"] == ["(assistant 응답 블록)"]  # 요청을 그대로 붙였다
    [result_block] = tool_results(calls[1])
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "n1"  # 요청 번호표와 짝이 맞는다
    assert result_block["is_error"] is False
    assert "대형 거래소 해킹" in result_block["content"]


def test_마지막_세_번째_호출은_답안_제출을_강제한다(loop):
    calls, responses, searched = loop
    responses += [news_request(), news_request(tool_id="n2"), raw(GOOD)]

    agent_service.analyze(None, req())

    assert [c["force_tool"] for c in calls] == [None, None, "submit_analysis"]
    assert len(searched) == 2  # 뉴스는 최대 2번까지


def test_두_도구를_모두_알려준다(loop):
    calls, responses, _ = loop
    responses.append(raw(GOOD))

    agent_service.analyze(None, req())

    names = [t["name"] for t in calls[0]["tools"]]
    assert names == ["get_news", "submit_analysis"]
    assert calls[0]["force_tool"] is None  # 첫 호출은 Claude가 고른다


def test_도구를_여러_개_한꺼번에_요청하면_모두_결과를_돌려준다(loop):
    calls, responses, searched = loop
    two = news_request(tool_id="a")
    two["tool_uses"].append({"id": "b", "name": "get_news", "input": {"days": 3}})
    responses += [two, raw(GOOD)]

    agent_service.analyze(None, req())

    # 요청 id마다 결과가 하나씩 있어야 한다 (빠지면 실제 API가 에러를 낸다)
    assert [b["tool_use_id"] for b in tool_results(calls[1])] == ["a", "b"]
    assert len(searched) == 2


def test_뉴스_입력이_틀리면_에러_결과를_돌려주고_대화를_이어간다(loop):
    calls, responses, searched = loop
    responses += [news_request(days=9999), raw(GOOD)]

    result = agent_service.analyze(None, req())

    assert result["stance"] == "관망"  # 서버가 죽지 않고 끝까지 간다
    assert searched == []  # 잘못된 입력은 DB 조회까지 가지 않았다
    [result_block] = tool_results(calls[1])
    assert result_block["is_error"] is True
    assert "days" in result_block["content"]


def test_모르는_도구_요청은_에러_결과로_돌려준다(loop):
    calls, responses, _ = loop
    unknown = news_request()
    unknown["tool_uses"][0]["name"] = "delete_everything"
    responses += [unknown, raw(GOOD)]

    agent_service.analyze(None, req())

    [result_block] = tool_results(calls[1])
    assert result_block["is_error"] is True
    assert "delete_everything" in result_block["content"]


def test_답안과_뉴스를_같이_요청하면_답안으로_끝내고_뉴스는_조회하지_않는다(loop):
    calls, responses, searched = loop
    both = raw(GOOD)
    both["tool_uses"].append({"id": "n1", "name": "get_news", "input": {}})
    responses.append(both)

    result = agent_service.analyze(None, req())

    assert result["stance"] == "관망"
    assert len(calls) == 1
    assert searched == []


def test_도구_없이_글로만_답하면_그_시도는_버리고_처음부터_다시_한다(loop):
    calls, responses, _ = loop
    responses += [raw(None, "end_turn"), raw(GOOD)]

    result = agent_service.analyze(None, req())

    assert result["stance"] == "관망"
    assert len(calls) == 2
    # 두 번째 시도는 이전 대화를 이어받지 않고 새로 시작한다 (메시지 1개)
    assert len(calls[1]["messages"]) == 1


def test_뉴스를_본_뒤에도_양식이_깨지면_재시도_횟수까지만_한다(loop):
    calls, responses, _ = loop
    bad = raw({**GOOD, "stance": "BUY"})
    # 1번 시도: 뉴스 조회 -> 깨진 답안 / 2번 시도: 깨진 답안
    responses += [news_request(), bad, bad]

    with pytest.raises(agent_service.AnalysisUnavailableError):
        agent_service.analyze(None, req())

    assert len(calls) == 3
