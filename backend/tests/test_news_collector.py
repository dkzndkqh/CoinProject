from app.clients import rss
from app.news import collector, service


class FakeSession:
    """SessionLocal()이 돌려주는 DB 세션 대신 쓰는 가짜. 호출 기록만 남기고 DB는 쓰지 않는다."""

    def __init__(self):
        self.rollbacks = 0
        self.closed = False

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def article(title: str, n: int = 1) -> dict:
    return {
        "url": f"https://x.com/{n}",
        "title": title,
        "summary": None,
        "published_at": None,
    }


def setup(monkeypatch, get_articles, save_articles=None):
    """collect_news가 쓰는 외부 의존(RSS, 저장, DB 세션)을 모두 가짜로 바꾼다."""
    session = FakeSession()
    monkeypatch.setattr(collector, "SessionLocal", lambda: session)
    monkeypatch.setattr(rss, "get_articles", get_articles)
    monkeypatch.setattr(
        service, "save_articles", save_articles or (lambda db, source, articles: 0)
    )
    return session


def test_관련_있는_기사만_저장한다(monkeypatch):
    saved_calls = []

    def fake_save(db, source, articles):
        saved_calls.append((source, [a["title"] for a in articles]))
        return len(articles)

    setup(
        monkeypatch,
        lambda source: [
            article("Bitcoin up", 1),
            article("Anthropic releases AI model", 2),  # 걸러져야 함
            article("SEC sues exchange", 3),
        ],
        fake_save,
    )

    collector.collect_news()

    # 출처가 3곳이고 출처마다 같은 목록이 오므로 3번 저장 시도, 매번 관련 기사 2개만 넘어간다
    assert len(saved_calls) == len(rss.FEEDS)
    for _, titles in saved_calls:
        assert titles == ["Bitcoin up", "SEC sues exchange"]


def test_저장_함수에는_출처_이름이_넘어간다(monkeypatch):
    sources = []
    setup(
        monkeypatch,
        lambda source: [article("Bitcoin")],
        lambda db, source, articles: sources.append(source) or 1,
    )

    collector.collect_news()

    assert sources == list(rss.FEEDS)


def test_한_출처가_실패해도_나머지는_계속_수집한다(monkeypatch):
    attempted = []
    saved_sources = []

    def fake_get(source):
        attempted.append(source)
        if source == "cointelegraph":
            raise RuntimeError("사이트 장애 흉내")  # 이 출처만 일부러 실패
        return [article("Bitcoin")]

    session = setup(
        monkeypatch,
        fake_get,
        lambda db, source, articles: saved_sources.append(source) or 1,
    )

    collector.collect_news()

    assert attempted == list(rss.FEEDS)  # 3곳을 모두 시도했다
    assert "cointelegraph" not in saved_sources  # 실패한 곳은 저장되지 않았다
    assert len(saved_sources) == len(rss.FEEDS) - 1  # 나머지는 저장됐다
    assert session.rollbacks == 1  # 실패한 건 DB 트랜잭션을 되돌렸다


def test_저장_중_에러가_나도_나머지_출처를_계속한다(monkeypatch):
    saved_sources = []

    def fake_save(db, source, articles):
        if source == "coindesk":
            raise RuntimeError("DB 장애 흉내")
        saved_sources.append(source)
        return 1

    session = setup(monkeypatch, lambda source: [article("Bitcoin")], fake_save)

    collector.collect_news()

    assert saved_sources == ["cointelegraph", "decrypt"]
    assert session.rollbacks == 1


def test_끝나면_항상_세션을_닫는다(monkeypatch):
    session = setup(monkeypatch, lambda source: [])

    collector.collect_news()

    assert session.closed is True


def test_모든_출처가_실패해도_예외를_밖으로_내지_않는다(monkeypatch):
    def always_fail(source):
        raise RuntimeError("전부 장애")

    session = setup(monkeypatch, always_fail)

    collector.collect_news()  # 예외가 나면 테스트가 실패한다. 스케줄러 작업이 죽으면 안 되기 때문이다.

    assert session.rollbacks == len(rss.FEEDS)
    assert session.closed is True
