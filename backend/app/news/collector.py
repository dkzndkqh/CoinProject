import logging

from app.clients import rss
from app.core.db import SessionLocal
from app.news import service

logger = logging.getLogger(__name__)

COLLECT_INTERVAL_MINUTES = 15  # 수집 주기


def collect_news() -> None:
    """15분마다 호출된다. 출처마다 RSS를 받아 키워드로 거르고 새 기사만 저장한다.
    스케줄러가 별도 스레드에서 부르기 때문에 세션을 직접 열고 닫는다 (market/collector.py와 같은 방식).
    """
    db = SessionLocal()
    try:
        for source in rss.FEEDS:
            try:
                articles = rss.get_articles(source)
                relevant = [a for a in articles if service.is_relevant(a)]
                saved = service.save_articles(db, source, relevant)
                logger.info(
                    "뉴스 수집 %s: 받음 %d, 관련 %d, 새로 저장 %d",
                    source,
                    len(articles),
                    len(relevant),
                    saved,
                )
            except Exception:
                # 한 출처가 실패해도 나머지는 계속한다. 다음 주기에 다시 받는다.
                logger.exception("뉴스 수집 실패: %s", source)
                db.rollback()

    finally:
        db.close()
