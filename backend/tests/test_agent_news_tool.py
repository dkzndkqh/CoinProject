import json
from datetime import UTC, datetime

from app.agent import service as agent_service
from app.news import service as news_service


def article(**fields):
    """get_articles가 돌려주는 기사 한 건의 모양. 필요한 칸만 바꿔서 쓴다."""
    base = {
        "published_at": datetime(2026, 11, 11, 3, 0, tzinfo=UTC),  # KST로 12:00
        "source": "coindesk",
        "title": "SEC 관련 기사",
        "summary": "짧은 요약",
        "label": "negative",
        "score": -0.9683,
    }
    return {**base, **fields}


def fake_get_articles(monkeypatch, articles):
    """DB 없이 테스트하려고 news_service.get_articles를 가짜로 바꾼다.
    돌려주는 값: 호출 때 받은 (days, limit, sort)가 쌓이는 목록 (인자가 맞게 넘어갔는지 확인용).
    """
    seen = []

    def fake(db, days, limit, sort):
        seen.append((days, limit, sort))
        return articles

    monkeypatch.setattr(news_service, "get_articles", fake)
    return seen


def parse_articles(text):
    """<articles>...</articles> 안의 JSON을 파이썬 목록으로 되돌린다."""
    assert text.startswith("<articles>\n")
    assert text.endswith("\n</articles>")
    return json.loads(text.removeprefix("<articles>\n").removesuffix("\n</articles>"))


def test_정상_입력이면_기사를_태그로_감싸_돌려준다(monkeypatch):
    fake_get_articles(monkeypatch, [article()])

    text, is_error = agent_service._run_get_news(None, {})

    assert is_error is False
    [item] = parse_articles(text)
    assert item == {
        "published_kst": "2026-11-11 12:00 KST",  # UTC가 아니라 한국 시간
        "source": "coindesk",
        "title": "SEC 관련 기사",
        "summary": "짧은 요약",
        "sentiment": "negative",
        "score": -0.97,  # 소수 둘째 자리로 반올림
    }


def test_입력을_안_주면_기본값으로_조회한다(monkeypatch):
    seen = fake_get_articles(monkeypatch, [article()])

    agent_service._run_get_news(None, {})

    assert seen == [(30, 5, "recent")]


def test_입력값이_그대로_조회에_전달된다(monkeypatch):
    seen = fake_get_articles(monkeypatch, [article()])

    agent_service._run_get_news(None, {"days": 7, "limit": 3, "sort": "impact"})

    assert seen == [(7, 3, "impact")]


def test_요약은_300자까지만_주고_없으면_빈_글이다(monkeypatch):
    fake_get_articles(
        monkeypatch,
        [article(summary="가" * 500), article(summary=None, label=None, score=None)],
    )

    text, _ = agent_service._run_get_news(None, {})

    long_item, empty_item = parse_articles(text)
    assert len(long_item["summary"]) == agent_service.SUMMARY_MAX_CHARS == 300
    assert empty_item["summary"] == ""
    # 아직 분석 전인 기사는 라벨과 점수가 None 그대로 간다
    assert empty_item["sentiment"] is None
    assert empty_item["score"] is None


def test_범위를_벗어난_입력은_에러로_돌려주고_조회하지_않는다(monkeypatch):
    seen = fake_get_articles(monkeypatch, [article()])

    text, is_error = agent_service._run_get_news(None, {"days": 9999})

    assert is_error is True
    assert "입력이 잘못됐습니다" in text
    assert "days" in text  # Claude가 어느 값을 고쳐야 하는지 알 수 있다
    assert seen == []  # DB 조회까지 가지 않았다


def test_여러_칸이_틀리면_이유를_모두_알려준다(monkeypatch):
    fake_get_articles(monkeypatch, [])

    text, is_error = agent_service._run_get_news(None, {"limit": 0, "sort": "oldest"})

    assert is_error is True
    assert "limit" in text
    assert "sort" in text


def test_기사가_없으면_에러가_아닌_안내문을_돌려준다(monkeypatch):
    fake_get_articles(monkeypatch, [])

    text, is_error = agent_service._run_get_news(None, {})

    assert text == "조건에 맞는 기사가 없습니다."
    assert is_error is False  # 입력은 정상이고 결과가 0건일 뿐이다


def test_도구_설명서에_입력_칸_세_개가_있다():
    tool = agent_service.GET_NEWS_TOOL

    assert tool["name"] == "get_news"
    assert set(tool["input_schema"]["properties"]) == {"days", "limit", "sort"}
