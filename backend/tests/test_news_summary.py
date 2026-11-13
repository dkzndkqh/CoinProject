from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.core.db import SessionLocal
from app.news.models import NewsArticle
from app.news.service import get_articles, get_sentiment_summary


@pytest.fixture
def db():
    """이 파일 테스트 전용 세션. 진짜 기사와 섞이지 않게 하는 방법이 핵심이다.

    요약 함수는 구간 안의 모든 기사를 세기 때문에, DB에 진짜 기사가 있으면 기대값이 틀어진다.
    그래서 같은 트랜잭션 안에서 기사 전체를 지우고(DELETE) 테스트 기사만 넣은 뒤,
    끝에서 rollback으로 전부 되돌린다. commit을 한 번도 하지 않으므로 진짜 기사는 그대로 남는다.
    (자바 테스트의 @Transactional 자동 롤백과 같은 방식이다.)
    주의: 이 파일에서 db.commit()을 쓰면 진짜 기사가 지워지니 절대 쓰지 않는다.
    """
    session = SessionLocal()
    session.execute(delete(NewsArticle))
    yield session
    session.rollback()
    session.close()


_counter = 0


def add(db, hours_ago: float, label: str | None, score: float | None) -> None:
    """지금부터 hours_ago시간 전에 발행된 기사를 넣는다 (commit 없이 flush만).
    경계(24시간, 168시간, 720시간)에서 정확히 떨어지는 값은 테스트 도중 시계가 움직여 흔들리므로,
    호출하는 쪽에서 경계에서 1시간 이상 떨어진 값만 쓴다.
    """
    global _counter
    _counter += 1  # url은 중복되면 안 되므로 호출마다 번호를 올린다
    db.add(
        NewsArticle(
            url=f"https://test.example/summary/{_counter}",
            title=f"기사 {_counter}",
            source="test-source",
            published_at=datetime.now(UTC) - timedelta(hours=hours_ago),
            sentiment_label=label,
            sentiment_score=score,
        )
    )
    db.flush()  # DB에 보내되 확정(commit)은 하지 않는다


def test_no_articles_gives_none_for_every_window(db):
    """기사가 하나도 없으면 세 구간 모두 None이다 (0건 요약이 아니라 '없음')."""
    assert get_sentiment_summary(db) == {
        "last_24h": None,
        "day2_to_7": None,
        "day8_to_30": None,
    }


def test_counts_and_average_in_one_window(db):
    """한 구간의 라벨별 개수와 평균 점수. 평균 = (0.8 + 0.4 - 0.6) / 3 = 0.2"""
    add(db, 2, "positive", 0.8)
    add(db, 5, "positive", 0.4)
    add(db, 10, "negative", -0.6)

    last = get_sentiment_summary(db)["last_24h"]

    assert last == {
        "scored_count": 3,
        "positive": 2,
        "negative": 1,
        "neutral": 0,
        "avg_score": 0.2,
    }


def test_each_article_lands_in_exactly_one_window(db):
    """구간이 겹치지 않는다: 기사 하나는 한 구간에만 센다. 30일보다 오래된 기사는 어디에도 안 센다."""
    add(db, 2, "positive", 0.5)  # last_24h
    add(db, 30, "negative", -0.5)  # 24시간 ~ 7일 -> day2_to_7
    add(db, 200, "neutral", 0.0)  # 7일 ~ 30일 -> day8_to_30 (200시간 = 약 8.3일)
    add(db, 800, "negative", -0.9)  # 30일(720시간) 초과 -> 어디에도 안 센다

    summary = get_sentiment_summary(db)

    assert summary["last_24h"]["scored_count"] == 1
    assert summary["last_24h"]["positive"] == 1
    assert summary["day2_to_7"]["scored_count"] == 1
    assert summary["day2_to_7"]["negative"] == 1
    assert summary["day8_to_30"]["scored_count"] == 1
    assert summary["day8_to_30"]["neutral"] == 1
    # 세 구간 합이 30일 안의 기사 수(3건)와 같다 = 중복 집계도 누락도 없다
    assert sum(w["scored_count"] for w in summary.values()) == 3


def test_unscored_articles_are_not_counted(db):
    """FinBERT 점수가 아직 없는 기사는 세지 않는다. 점수 없는 기사만 있으면 그 구간은 None이다."""
    add(db, 2, None, None)

    assert get_sentiment_summary(db)["last_24h"] is None


def test_get_articles_recent_is_newest_first_and_respects_limit(db):
    """sort="recent": 최신 기사가 먼저 온다. limit개까지만 돌려준다. 점수로 구분하려고 서로 다른 값을 쓴다."""
    add(db, 50, "neutral", 0.1)  # 가장 오래됨
    add(db, 10, "neutral", 0.2)
    add(db, 1, "neutral", 0.3)  # 가장 최신

    scores = [a["score"] for a in get_articles(db, days=30, limit=2, sort="recent")]

    assert scores == [0.3, 0.2]


def test_get_articles_impact_orders_by_absolute_score(db):
    """sort="impact": 점수 절댓값이 큰 순. -0.9와 +0.5는 -0.9가 먼저 온다(음수도 큰 영향으로 본다).
    점수 없는 기사는 최신이어도 맨 뒤다.
    """
    add(db, 1, None, None)  # 점수 없음: 가장 최신이지만 맨 뒤
    add(db, 20, "positive", 0.5)
    add(db, 30, "negative", -0.9)
    add(db, 40, "neutral", 0.1)

    scores = [a["score"] for a in get_articles(db, days=30, limit=10, sort="impact")]

    assert scores == [-0.9, 0.5, 0.1, None]


def test_get_articles_excludes_articles_older_than_days(db):
    """days 밖의 기사는 빠진다. 3일 이내만 요청하면 5일 전 기사는 안 나온다."""
    add(db, 10, "neutral", 0.1)  # 10시간 전: 포함
    add(db, 120, "negative", -0.9)  # 5일 전: 제외

    scores = [a["score"] for a in get_articles(db, days=3, limit=10, sort="impact")]

    assert scores == [0.1]
