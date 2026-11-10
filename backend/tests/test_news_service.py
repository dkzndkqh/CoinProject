from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.news import service
from app.news.models import NewsArticle

# 테스트 전용 주소 접두사. 진짜 기사와 섞이지 않고, 테스트 뒤 이 접두사의 행만 지운다.
TEST_PREFIX = "https://test.example/"


def make_article(n=1, title="Bitcoin rallies", summary="요약", **extra) -> dict:
    """rss.get_articles()가 돌려주는 모양의 기사 dict 하나."""
    return {
        "url": f"{TEST_PREFIX}{n}",
        "title": title,
        "summary": summary,
        "published_at": datetime(2026, 11, 10, 5, 0, tzinfo=UTC),
        **extra,
    }


# ---- is_relevant (키워드 필터) ----


@pytest.mark.parametrize(
    "title",
    [
        "Bitcoin hits new high",  # 대문자로 시작
        "BTC dips below $70,000",  # 약어
        "Ethereum upgrade delayed",
        "Ether staking hits record",
        "ETH ETF inflows surge",
        "SEC delays decision on new filings",  # 규제 기관
        "CFTC sues exchange",
        "New regulation targets exchanges",  # regulat* 어미 변화
        "Regulators weigh stablecoin rules",
        "Greece passes tax law on gains",  # 세금
        "Fed signals rate pause",
        "Interest rates stay high",
        "Stablecoin supply grows",
    ],
)
def test_키워드가_제목에_있으면_통과한다(title):
    assert service.is_relevant({"title": title, "summary": None}) is True


def test_키워드가_요약에만_있어도_통과한다():
    article = {"title": "Market wrap", "summary": "Bitcoin fell 2% overnight."}
    assert service.is_relevant(article) is True


def test_대소문자는_구분하지_않는다():
    assert service.is_relevant({"title": "bItCoIn", "summary": None}) is True


@pytest.mark.parametrize(
    "title",
    [
        "Anthropic releases new AI model",  # 코인과 무관
        "Nvidia unveils new chips",
        "Solana wallet adds new feature",  # 다른 코인
        "XRP Ledger maps out quantum-proof accounts",
        "A new method for testing",  # 'eth'가 method 안에 들어 있다. 단어 경계라서 안 걸려야 한다
        "Second quarter results",  # 'sec'가 second 안에 들어 있다
    ],
)
def test_키워드가_없으면_걸러진다(title):
    assert service.is_relevant({"title": title, "summary": None}) is False


def test_crypto라는_단어만으로는_통과하지_않는다():
    # 노이즈가 많아서 키워드에서 뺐다 (CLAUDE.md 4단계 결정). 다시 넣으면 이 테스트가 알려 준다.
    article = {
        "title": "Crypto card provider says hackers accessed data",
        "summary": None,
    }
    assert service.is_relevant(article) is False


def test_요약이_None이어도_에러_없이_제목만_본다():
    assert service.is_relevant({"title": "Hello", "summary": None}) is False
    assert service.is_relevant({"title": "Bitcoin", "summary": None}) is True


# ---- save_articles (DB 사용) ----


def _clean(session):
    session.execute(delete(NewsArticle).where(NewsArticle.url.like(f"{TEST_PREFIX}%")))
    session.commit()


@pytest.fixture
def db():
    """DB 세션을 주고, 테스트 전후로 테스트용 기사만 지운다 (JUnit의 @BeforeEach/@AfterEach)."""
    session = SessionLocal()
    _clean(session)
    yield session
    session.rollback()
    _clean(session)
    session.close()


def _get(db, n) -> NewsArticle:
    return db.execute(
        select(NewsArticle).where(NewsArticle.url == f"{TEST_PREFIX}{n}")
    ).scalar_one()


def test_새_기사를_저장하고_개수를_돌려준다(db):
    saved = service.save_articles(db, "test-source", [make_article(1), make_article(2)])

    assert saved == 2
    row = _get(db, 1)
    assert row.source == "test-source"  # 출처는 저장 함수가 붙인다
    assert row.title == "Bitcoin rallies"
    assert row.published_at == datetime(2026, 11, 10, 5, 0, tzinfo=UTC)
    assert row.sentiment_score is None  # 감성 점수는 아직 없다
    assert row.fetched_at is not None  # DB가 채운다


def test_빈_목록은_0을_돌려준다(db):
    assert service.save_articles(db, "test-source", []) == 0


def test_같은_url은_다시_저장하지_않는다(db):
    service.save_articles(db, "test-source", [make_article(1)])

    saved = service.save_articles(db, "test-source", [make_article(1)])

    assert saved == 0


def test_이미_있는_기사는_덮어쓰지_않는다(db):
    # 감성 점수가 붙은 기사를 RSS에서 다시 받아도 점수가 지워지면 안 된다
    service.save_articles(db, "test-source", [make_article(1, title="원래 제목")])
    row = _get(db, 1)
    row.sentiment_score = 0.7
    row.sentiment_label = "positive"
    db.commit()

    service.save_articles(db, "test-source", [make_article(1, title="바뀐 제목")])

    db.expire_all()  # 캐시를 버리고 DB에서 다시 읽는다
    row = _get(db, 1)
    assert row.title == "원래 제목"
    assert row.sentiment_score == 0.7
    assert row.sentiment_label == "positive"


def test_새_기사와_기존_기사가_섞이면_새_것만_센다(db):
    service.save_articles(db, "test-source", [make_article(1)])

    saved = service.save_articles(
        db, "test-source", [make_article(1), make_article(2), make_article(3)]
    )

    assert saved == 2


def test_요약이_없는_기사도_저장된다(db):
    service.save_articles(db, "test-source", [make_article(1, summary=None)])

    assert _get(db, 1).summary is None
