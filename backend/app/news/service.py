import re

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.news.models import NewsArticle

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
