from datetime import UTC, datetime

import httpx
import pytest

from app.clients import rss

# ---- 가짜 HTTP 응답 ----
# rss.get_articles는 내부에서 httpx.Client를 만들어 쓴다. 테스트에서는 진짜 네트워크를 쓰지 않고
# 이 가짜 클라이언트로 바꿔서, 정해 둔 XML을 받은 것처럼 만든다 (자바의 Mockito mock과 같은 역할).


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        # 진짜 httpx처럼 4xx, 5xx면 HTTPStatusError를 던진다
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "bad status",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(self.status_code),
            )


def serve(monkeypatch, content: str, status_code: int = 200):
    """rss.httpx.Client를 가짜로 바꿔서 get()이 content를 돌려주게 한다."""

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        # with 문에서 쓰이려면 __enter__, __exit__이 필요하다 (자바 AutoCloseable과 비슷)
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse(content.encode("utf-8"), status_code)

    monkeypatch.setattr(rss.httpx, "Client", FakeClient)


def feed(*items: str) -> str:
    """<item> 문자열들을 RSS 문서로 감싼다."""
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{"".join(items)}</channel></rss>'


def item(
    title="제목",
    link="https://a.com/x",
    pub="Tue, 10 Nov 2026 05:18:31 +0000",
    desc="요약",
) -> str:
    """<item> 하나. 값을 None으로 주면 그 태그를 아예 뺀다 (필수 칸이 빠진 기사를 만들려고)."""
    parts = []
    if title is not None:
        parts.append(f"<title>{title}</title>")
    if link is not None:
        parts.append(f"<link>{link}</link>")
    if pub is not None:
        parts.append(f"<pubDate>{pub}</pubDate>")
    if desc is not None:
        parts.append(f"<description>{desc}</description>")
    return f"<item>{''.join(parts)}</item>"


# ---- _clean_text ----


def test_HTML_태그를_지우고_글만_남긴다():
    raw = '<p style="float:right"><img src="a.jpg"></p><p>Cold storage is useful. </p>'
    assert rss._clean_text(raw) == "Cold storage is useful."


def test_HTML_문자를_원래_글자로_바꾼다():
    assert rss._clean_text("AT&amp;T said &quot;yes&quot;") == 'AT&T said "yes"'


def test_줄바꿈과_연속_공백은_한_칸으로_줄인다():
    assert rss._clean_text("a   b\n\n c\t d") == "a b c d"


@pytest.mark.parametrize("raw", [None, "", "   \n  ", "<p></p>", "<img src='a'>  "])
def test_글이_없으면_None(raw):
    assert rss._clean_text(raw) is None


# ---- _parse_time ----


def test_RFC822_시각을_UTC로_읽는다():
    result = rss._parse_time("Tue, 10 Nov 2026 05:18:31 +0000")
    assert result == datetime(2026, 11, 10, 5, 18, 31, tzinfo=UTC)


def test_다른_시간대는_UTC로_변환한다():
    # 한국 시간 14:00 = UTC 05:00
    result = rss._parse_time("Tue, 10 Nov 2026 14:00:00 +0900")
    assert result == datetime(2026, 11, 10, 5, 0, 0, tzinfo=UTC)
    assert result.utcoffset().total_seconds() == 0


def test_시간대_표시가_없으면_UTC로_본다():
    # "-0000"은 시간대 정보가 없다는 표기라 naive datetime이 나온다
    result = rss._parse_time("Tue, 10 Nov 2026 05:18:31 -0000")
    assert result.tzinfo is not None
    assert result == datetime(2026, 11, 10, 5, 18, 31, tzinfo=UTC)


def test_형식이_틀린_시각은_ValueError():
    with pytest.raises(ValueError):
        rss._parse_time("어제 오후")


# ---- get_articles ----


def test_기사_목록을_정해진_모양으로_돌려준다(monkeypatch):
    # 실제 RSS처럼 HTML을 XML 안에 이스케이프해서 넣는다 (&lt;p&gt; = <p>)
    serve(monkeypatch, feed(item(title="Bitcoin up", desc="&lt;p&gt;Rally&lt;/p&gt;")))

    articles = rss.get_articles("coindesk")

    assert articles == [
        {
            "url": "https://a.com/x",
            "title": "Bitcoin up",
            "summary": "Rally",
            "published_at": datetime(2026, 11, 10, 5, 18, 31, tzinfo=UTC),
        }
    ]


def test_주소의_추적용_쿼리는_잘라낸다(monkeypatch):
    # 같은 기사가 다른 주소로 저장돼 url 중복 방지를 통과하는 걸 막는다
    # XML 안의 &는 &amp;로 적어야 한다
    serve(
        monkeypatch,
        feed(item(link="https://a.com/x?utm_source=rss&amp;utm_medium=rss")),
    )

    assert rss.get_articles("cointelegraph")[0]["url"] == "https://a.com/x"


def test_주소_앞뒤_공백은_지운다(monkeypatch):
    serve(monkeypatch, feed(item(link="  https://a.com/x \n")))

    assert rss.get_articles("decrypt")[0]["url"] == "https://a.com/x"


def test_요약이_없는_기사는_summary가_None이다(monkeypatch):
    serve(monkeypatch, feed(item(desc=None)))

    articles = rss.get_articles("coindesk")

    assert len(articles) == 1
    assert articles[0]["summary"] is None


@pytest.mark.parametrize(
    "bad_item",
    [
        item(title=None),  # 제목 없음
        item(link=None),  # 주소 없음
        item(pub=None),  # 발행 시각 없음
        item(title="<p></p>"),  # 제목이 태그뿐이라 비어 버림
        item(pub="어제 오후"),  # 시각을 읽을 수 없음
    ],
)
def test_필수_칸이_없거나_읽을_수_없는_기사는_건너뛴다(monkeypatch, bad_item):
    good = item(title="정상", link="https://a.com/ok")
    serve(monkeypatch, feed(bad_item, good))

    articles = rss.get_articles("coindesk")

    # 나쁜 기사만 빠지고 정상 기사는 남는다
    assert [a["title"] for a in articles] == ["정상"]


def test_기사_순서는_피드_순서_그대로다(monkeypatch):
    serve(
        monkeypatch,
        feed(
            item(title="first", link="https://a.com/1"),
            item(title="second", link="https://a.com/2"),
        ),
    )

    assert [a["title"] for a in rss.get_articles("coindesk")] == ["first", "second"]


def test_기사가_없는_피드는_빈_목록(monkeypatch):
    serve(monkeypatch, feed())

    assert rss.get_articles("coindesk") == []


def test_HTTP_에러는_그대로_올라간다(monkeypatch):
    # 한 출처가 실패해도 다른 출처를 계속하는 건 서비스(4-3)의 몫이다
    serve(monkeypatch, "", status_code=500)

    with pytest.raises(httpx.HTTPStatusError):
        rss.get_articles("coindesk")


def test_모르는_출처는_KeyError():
    with pytest.raises(KeyError):
        rss.get_articles("unknown")


def test_FEEDS에_영어_출처_세_곳이_있다():
    assert set(rss.FEEDS) == {"coindesk", "cointelegraph", "decrypt"}
