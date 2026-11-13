import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.news.models import NewsArticle

# 구간 이름 -> (더 최근 경계, 더 오래된 경계). 지금부터 "몇 시간 전"인지로 적는다.
# 서로 겹치지 않아서 기사 한 건은 한 구간에만 들어간다.
# 예: day2_to_7 = 24시간 전 ~ 168시간(7일) 전에 발행된 기사
NEWS_WINDOWS = {
    "last_24h": (0, 24),
    "day2_to_7": (24, 24 * 7),
    "day8_to_30": (24 * 7, 24 * 30),
}

# 코인 시장 분위기에 영향을 줄 만한 기사를 고르는 키워드. 제목이나 요약에 하나라도 있으면 통과한다.
# - BTC·ETH 직접 언급: bitcoin, btc, ethereum, ether, eth
# - 시장 전체에 영향을 주는 주제: stablecoin, etf, sec, cftc, 규제(regulat*), 세금, 금리 등
# 수집해 보고 노이즈가 많거나 놓치는 기사가 있으면 이 목록만 고치면 된다.
# \b : 단어 경계. "eth"가 "method" 안에서 걸리지 않고 단어로 따로 쓰였을 때만 맞게 한다.
# \w* : regulat 뒤에 글자가 더 붙어도 맞게 한다 (regulation, regulatory, regulators...)
# re.IGNORECASE : 대소문자 구분 안 함 (자바 Pattern.CASE_INSENSITIVE)
KEYWORD_RE = re.compile(
    r"\b(bitcoin|btc|ethereum|ether|eth|stablecoins?|etfs?|sec|cftc"
    r"|regulat\w*|tax(es)?|fed|interest rates?)\b",
    re.IGNORECASE,
)


def is_relevant(article: dict) -> bool:
    """제목이나 요약에 키워드가 있으면 True. 요약이 None일 수 있어서 `or ""`로 빈 글로 바꾼다."""
    text = f"{article['title']} {article['summary'] or ''}"
    return KEYWORD_RE.search(text) is not None


def save_articles(db: Session, source: str, articles: list[dict]) -> int:
    """기사들을 저장하고, 새로 저장된 개수를 돌려준다. 같은 url은 건너뛴다 (덮어쓰지 않음).
    articles: rss.get_articles()가 준 dict 목록. source는 저장할 때 각 행에 붙인다.
    """
    if not articles:
        return 0

    # 각 기사 dict에 출처 칸을 더해 DB 행 모양으로 만든다.
    # {**article, "source": source}: 기존 dict를 펼치고 source를 추가한 새 dict (자바에 없는 문법)
    rows = [{**article, "source": source} for article in articles]

    # on_conflict_do_nothing: url이 이미 있으면 그 행은 무시한다. 에러 없이 건너뛴다.
    # returning(NewsArticle.id): 실제로 새로 들어간 행의 id만 돌려받는다.
    # (rowcount는 이 방식에서 -1이 나와 믿을 수 없어서, kronos_forecasts 저장 때와 같은 방법을 쓴다)
    stmt = (
        insert(NewsArticle)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["url"])
        .returning(NewsArticle.id)
    )
    saved = db.execute(stmt).all()
    db.commit()
    return len(saved)


def get_unscored(db: Session, limit: int) -> list[dict]:
    """감성 점수가 아직 없는 기사를 최신순으로 limit개 돌려준다.
    최신 기사가 시장 분위기에 더 중요해서 최신순으로 준다.
    `.is_(None)`은 SQL의 IS NULL이다. 파이썬의 `== None`은 쓰지 않는다
    (SQLAlchemy가 연산자를 가로채 SQL로 바꾸는 방식이라 is_를 쓰는 게 정석이다).
    """
    stmt = (
        select(NewsArticle.id, NewsArticle.title, NewsArticle.summary)
        .where(NewsArticle.sentiment_score.is_(None))
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
    )
    return [
        {"id": r.id, "title": r.title, "summary": r.summary}
        for r in db.execute(stmt).all()
    ]


def save_sentiments(db: Session, items: list) -> int:
    """기사별 감성 결과를 저장하고, 실제로 저장된 건수를 돌려준다.
    이미 점수가 있는 기사는 건너뛴다 (WHERE sentiment_score IS NULL).
    같은 요청을 두 번 보내거나 두 곳에서 동시에 계산해도 먼저 저장된 값이 유지된다.
    ponytail: 건별 UPDATE. 한 번에 최대 200건이라 충분하다. 더 늘어나면 한 번에 묶는 UPDATE로 바꾼다.
    """
    updated = 0
    for item in items:
        stmt = (
            update(NewsArticle)
            .where(NewsArticle.id == item.id, NewsArticle.sentiment_score.is_(None))
            .values(
                sentiment_label=item.label,
                sentiment_score=item.score,
                model_name=item.model_name,
            )
            .returning(NewsArticle.id)  # 실제로 바뀐 행만 돌려받아 센다
        )
        if db.execute(stmt).first() is not None:
            updated += 1
    db.commit()
    return updated


def _summarize_window(db: Session, newer_hours: int, older_hours: int) -> dict | None:
    """한 구간의 요약을 만든다. 점수가 있는 기사의 라벨별 개수와 평균 점수.
    기사가 하나도 없으면 None.
    구간은 [older_hours 전, newer_hours 전) 이다. 시작은 포함, 끝은 제외라서
    경계 시각의 기사가 두 구간에 겹쳐 들어가지 않는다.
    """
    now = datetime.now(UTC)
    start = now - timedelta(hours=older_hours)
    end = now - timedelta(hours=newer_hours)

    # SQL: SELECT label, COUNT(*), AVG(score) FROM news_articles
    #      WHERE published_at >= start AND published_at < end AND score IS NOT NULL
    #      GROUP BY label
    # 결과: (라벨, 그 라벨의 기사 수, 그 라벨의 평균 점수) 묶음 목록
    stmt = (
        select(
            NewsArticle.sentiment_label,
            func.count(),
            func.avg(NewsArticle.sentiment_score),
        )
        .where(
            NewsArticle.published_at >= start,
            NewsArticle.published_at < end,
            NewsArticle.sentiment_score.is_not(None),  # SQL의 IS NOT NULL
        )
        .group_by(NewsArticle.sentiment_label)
    )

    counts = {"positive": 0, "negative": 0, "neutral": 0}
    score_sum = 0.0
    for label, count, avg in db.execute(stmt).all():
        counts[label] = count
        score_sum += count * avg

    total = sum(counts.values())
    if total == 0:
        return None
    return {
        "scored_count": total,
        **counts,
        "avg_score": round(score_sum / total, 2),
    }


def get_sentiment_summary(db: Session) -> dict:
    """구간별 요약을 한 묶음으로 돌려준다. 기사가 없는 구간 값은 None이다.
    딕셔너리 컴프리헨션: NEWS_WINDOWS의 (이름 -> 범위)마다 요약을 만들어 같은 이름으로 담는다.
    자바의 stream().collect(toMap(...))과 같다.
    """
    return {
        name: _summarize_window(db, newer, older)
        for name, (newer, older) in NEWS_WINDOWS.items()
    }


def get_articles(db: Session, days: int, limit: int, sort: str) -> list[dict]:
    """최근 days일 안에 발행된 기사를 limit개 돌려준다. 에이전트의 get_news 도구가 부른다.
    sort="recent": 최신순.
    sort="impact": 점수 절댓값이 큰 순 (아주 좋거나 아주 나쁜 기사부터). 점수 없는 기사는 맨 뒤.
    값의 범위 검사(days 1~30 등)는 이 함수가 아니라 호출하는 쪽에서 한다.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = select(NewsArticle).where(NewsArticle.published_at >= cutoff)

    if sort == "impact":
        # func.abs(): 절댓값. -0.9와 +0.9를 같은 크기로 본다.
        # .desc().nulls_last(): 큰 순서대로, NULL(점수 없음)은 맨 뒤로. SQL의 ORDER BY ... DESC NULLS LAST.
        # 점수가 같으면 최신 기사가 먼저 오게 두 번째 정렬 기준을 붙인다.
        stmt = stmt.order_by(
            func.abs(NewsArticle.sentiment_score).desc().nulls_last(),
            NewsArticle.published_at.desc(),
        )
    else:
        stmt = stmt.order_by(NewsArticle.published_at.desc())

    # db.scalars(): 행마다 첫 칸(여기서는 NewsArticle 객체)만 꺼낸다.
    # 시각은 UTC datetime 그대로 둔다. KST 문자열로 바꾸는 건 에이전트 쪽 몫이다.
    return [
        {
            "published_at": a.published_at,
            "source": a.source,
            "title": a.title,
            "summary": a.summary,
            "label": a.sentiment_label,
            "score": a.sentiment_score,
        }
        for a in db.scalars(stmt.limit(limit))
    ]
