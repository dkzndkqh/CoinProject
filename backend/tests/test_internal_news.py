from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.main import app
from app.news import service
from app.news.models import NewsArticle

# 서버를 띄우지 않고 메모리에서 요청을 보낸다 (자바 MockMvc와 같다).
# with 없이 쓰는 이유: lifespan(스케줄러, 캔들 복구)이 실행되면 외부 API를 부르기 때문이다.
client = TestClient(app)

HEADERS = {"X-API-Key": settings.internal_api_key}
UNSCORED = "/api/internal/news/unscored"
SENTIMENT = "/api/internal/news/sentiment"

# 테스트 기사에만 붙이는 표시. 진짜 기사와 섞이지 않고, 끝나면 이 접두사의 행만 지운다.
TEST_PREFIX = "https://test.example/internal/"
# 발행 시각을 2100년으로 둔다: "최신순" 조회에서 진짜 기사보다 항상 앞에 와서,
# limit을 테스트 기사 수에 맞추면 테스트 기사만 정확히 돌려받는다.
FUTURE = datetime(2100, 1, 1, tzinfo=UTC)


def _clean(session):
    session.execute(delete(NewsArticle).where(NewsArticle.url.like(f"{TEST_PREFIX}%")))
    session.commit()


@pytest.fixture(autouse=True)
def real_db_for_app():
    """이 파일의 요청은 진짜 DB를 쓴다.
    다른 테스트(test_agent_router 등)가 모듈 맨 위에서 get_db를 가짜로 바꿔 두고 되돌리지 않아서,
    전체를 같이 돌리면 여기까지 가짜(None)가 넘어온다. 그래서 이 파일 테스트 동안만 진짜로 덮어쓰고,
    끝나면 원래 설정으로 되돌려 놓는다.
    autouse=True: 이 파일의 모든 테스트에 자동으로 적용한다.
    """
    previous = app.dependency_overrides.get(get_db)

    def real_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = real_get_db
    yield
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


@pytest.fixture
def db():
    session = SessionLocal()
    _clean(session)
    yield session
    session.rollback()
    _clean(session)
    session.close()


def add_articles(db, count: int) -> list[int]:
    """테스트 기사 count개를 저장하고 id 목록을 돌려준다. n이 클수록 더 최신이다."""
    articles = [
        {
            "url": f"{TEST_PREFIX}{n}",
            "title": f"기사 {n}",
            "summary": None if n == 1 else f"요약 {n}",
            "published_at": FUTURE + timedelta(minutes=n),
        }
        for n in range(1, count + 1)
    ]
    service.save_articles(db, "test-source", articles)
    rows = db.execute(
        select(NewsArticle.id)
        .where(NewsArticle.url.like(f"{TEST_PREFIX}%"))
        .order_by(NewsArticle.published_at)
    ).all()
    return [r.id for r in rows]


def item(article_id: int, **override) -> dict:
    return {
        "id": article_id,
        "label": "positive",
        "score": 0.75,
        "model_name": "ProsusAI/finbert",
        **override,
    }


def upload(*items: dict):
    return client.post(SENTIMENT, json={"results": list(items)}, headers=HEADERS)


def get_row(db, article_id: int) -> NewsArticle:
    db.expire_all()  # 캐시를 버리고 DB에서 다시 읽는다
    return db.get(NewsArticle, article_id)


# ---- 인증 ----


@pytest.mark.parametrize(
    "headers", [{}, {"X-API-Key": "wrong-key"}], ids=["키 없음", "틀린 키"]
)
def test_키가_없거나_틀리면_두_API_모두_401(headers):
    assert client.get(UNSCORED, headers=headers).status_code == 401
    response = client.post(SENTIMENT, json={"results": []}, headers=headers)
    assert response.status_code == 401


# ---- 조회: 뉴스 분석 전인 기사 ----


def test_분석_전인_기사를_최신순으로_돌려준다(db):
    ids = add_articles(db, 3)  # 오래된 순: ids[0] < ids[1] < ids[2]

    response = client.get(UNSCORED, params={"limit": 3}, headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert [a["id"] for a in body] == [ids[2], ids[1], ids[0]]  # 최신이 먼저
    # 응답은 id, title, summary 세 칸만 준다
    assert set(body[0]) == {"id", "title", "summary"}
    assert body[0]["title"] == "기사 3"
    assert body[2]["summary"] is None  # 요약이 없는 기사도 그대로 나온다


def test_이미_분석된_기사는_조회에서_빠진다(db):
    ids = add_articles(db, 3)
    assert upload(item(ids[2])).json() == {"updated": 1}  # 가장 최신 기사를 분석 완료로

    response = client.get(UNSCORED, params={"limit": 2}, headers=HEADERS)

    # limit=2인데 분석된 기사를 건너뛰고 남은 테스트 기사 2개가 나온다
    assert [a["id"] for a in response.json()] == [ids[1], ids[0]]


def test_limit만큼만_돌려준다(db):
    add_articles(db, 3)

    response = client.get(UNSCORED, params={"limit": 2}, headers=HEADERS)

    assert len(response.json()) == 2


@pytest.mark.parametrize("limit", [0, 201, -1])
def test_limit이_범위를_벗어나면_422(limit):
    response = client.get(UNSCORED, params={"limit": limit}, headers=HEADERS)

    assert response.status_code == 422


# ---- 업로드 ----


def test_분석_결과를_저장하고_건수를_돌려준다(db):
    ids = add_articles(db, 2)

    response = upload(
        item(ids[0], label="positive", score=0.75),
        item(ids[1], label="negative", score=-0.5, model_name="other-model"),
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 2}
    first, second = get_row(db, ids[0]), get_row(db, ids[1])
    assert (first.sentiment_label, first.sentiment_score) == ("positive", 0.75)
    assert first.model_name == "ProsusAI/finbert"
    assert (second.sentiment_label, second.sentiment_score) == ("negative", -0.5)
    assert second.model_name == "other-model"


def test_이미_분석된_기사는_덮어쓰지_않는다(db):
    (article_id,) = add_articles(db, 1)
    upload(item(article_id, label="positive", score=0.75))

    response = upload(item(article_id, label="negative", score=-0.9, model_name="x"))

    assert response.json() == {"updated": 0}  # 새로 저장된 게 없다
    row = get_row(db, article_id)
    assert (row.sentiment_label, row.sentiment_score) == ("positive", 0.75)
    assert row.model_name == "ProsusAI/finbert"


def test_새_기사와_분석된_기사가_섞이면_새_것만_센다(db):
    ids = add_articles(db, 3)
    upload(item(ids[0]))

    response = upload(item(ids[0]), item(ids[1]), item(ids[2]))

    assert response.json() == {"updated": 2}


def test_없는_기사_id는_세지_않고_에러도_아니다(db):
    (article_id,) = add_articles(db, 1)

    response = upload(item(article_id), item(2_000_000_000))

    assert response.status_code == 200
    assert response.json() == {"updated": 1}


def test_경계값_score는_저장된다(db):
    ids = add_articles(db, 2)

    response = upload(item(ids[0], score=1), item(ids[1], score=-1, label="negative"))

    assert response.json() == {"updated": 2}
    assert get_row(db, ids[0]).sentiment_score == 1
    assert get_row(db, ids[1]).sentiment_score == -1


def test_중립_label도_저장된다(db):
    (article_id,) = add_articles(db, 1)

    upload(item(article_id, label="neutral", score=0.0))

    row = get_row(db, article_id)
    assert (row.sentiment_label, row.sentiment_score) == ("neutral", 0.0)


# ---- 업로드 입력 검증 (서비스에 가기 전에 422로 막는다) ----


@pytest.mark.parametrize(
    "bad",
    [
        {"score": 1.5},  # 범위 초과
        {"score": -1.01},
        {"label": "great"},  # 허용되지 않은 label
        {"model_name": ""},  # 빈 모델 이름
        {"model_name": "x" * 51},  # 너무 긴 모델 이름
        {"score": "abc"},  # 숫자가 아님
        {"id": "abc"},  # id가 숫자가 아님
    ],
)
def test_잘못된_항목은_422이고_저장되지_않는다(db, bad):
    (article_id,) = add_articles(db, 1)

    response = upload(item(article_id, **bad))

    assert response.status_code == 422
    assert get_row(db, article_id).sentiment_score is None


def test_빈_목록과_200건_초과는_422():
    assert upload().status_code == 422
    many = [item(1)] * 201
    assert (
        client.post(SENTIMENT, json={"results": many}, headers=HEADERS).status_code
        == 422
    )


def test_필수_칸이_빠지면_422():
    bad = {"id": 1, "label": "positive", "score": 0.5}  # model_name 없음
    response = client.post(SENTIMENT, json={"results": [bad]}, headers=HEADERS)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
