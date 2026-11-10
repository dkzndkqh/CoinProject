import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

# 수집할 RSS 주소. 키는 DB의 source 칸에 들어가는 이름이다.
# 블록미디어(한국어)는 FinBERT가 영어 전용이라 지금은 뺐다.
FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
}

TIMEOUT = 10.0

# 특정 사이트 프로그램 http 요청 거부를 방지
HEADERS = {"User-Agent": "Mozilla/5.0"}

# HTML 태그(<...>)를 찾는 정규식. [^>]+ 는 ">"가 아닌 글자가 1개 이상이라는 뜻이다.
TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(raw: str | None) -> str | None:
    """RSS 글을 사람이 읽는 평문으로 바꾼다. 내용이 없으면 None.
    Cointelegraph의 요약처럼 HTML 태그가 섞인 글이 있어서 태그를 지우고,
    &amp; 같은 HTML 문자를 원래 글자로 바꾸고, 줄바꿈·연속 공백을 한 칸으로 줄인다.
    """

    if not raw:
        return None
    text = TAG_RE.sub(
        "", raw
    )  # sub(바꿀 것, 문자열): 태그를 빈 문자열로 치환 (자바 replaceAll)
    text = html.unescape(text)  # "&amp;" -> "&" (자바 StringEscapeUtils.unescapeHtml4)
    # split()은 공백,줄바꿈 덩어리를 기준으로 자르고 " ".join()이 한 칸 공백으로 다시 붙임.
    text = " ".join(text.split())
    return text or None  # 빈 문자열이면 None


def _parse_time(raw: str) -> datetime:
    """RSS의 발행 시각을 UTC datetime으로 바꾼다. 예: "Tue, 10 Nov 2026 05:18:31 +0000".
    표준 라이브러리 parsedate_to_datetime이 이 형식(RFC 822)을 읽는다.
    형식이 틀리면 ValueError가 난다.
    """
    dt = parsedate_to_datetime(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def get_articles(source: str) -> list[dict]:
    """한 출처의 RSS를 받아 기사 목록으로 돌려준다 (최신 기사부터, 보통 25~40개).
    돌려주는 모양: [{"url", "title", "summary"(없으면 None), "published_at"(UTC)}, ...]
    키워드 걸러내기와 DB 저장은 서비스(4-3)가 한다. 여기서는 받아서 정리만 한다.
    네트워크·HTTP 에러는 그대로 올라간다 (한 출처가 실패해도 다른 출처를 계속하는 건 서비스의 몫).
    source: FEEDS의 키. 모르는 이름이면 KeyError.
    """
    url = FEEDS[source]

    with httpx.Client(
        timeout=TIMEOUT, headers=HEADERS, follow_redirects=True
    ) as client:
        response = client.get(url)
        response.raise_for_status()

    # response.content: 바이트 그대로. XML 첫 줄에 인코딩이 적혀 있어서 바이트로 넘기면 알아서 읽는다.
    # response.text(문자열)로 넘기면 인코딩 선언과 충돌할 수 있다.
    root = ET.fromstring(response.content)

    articles = []
    # root.iter("item"): 문서 안의  모든 <item> 태그를 차례로 돈다
    for item in root.iter("item"):
        # findtext("태그"): 그 하위 태그의 글자를 꺼냄
        link = item.findtext("link")
        title = _clean_text(item.findtext("title"))
        published = item.findtext("pubDate")
        if not (link and title and published):
            continue

        try:
            published_at = _parse_time(published)
        except (TypeError, ValueError):
            continue

        articles.append(
            {
                # 주소 뒤의 ?utm_source=같은 추적용 쿼리 잘라내기
                # 안 자르면 같은 기사가 다른 주소로 저장돼 url 중복 방지 통과
                "url": link.strip().split("?")[0],
                "title": title,
                "summary": _clean_text(item.findtext("description")),
                "published_at": published_at,
            }
        )
    return articles
