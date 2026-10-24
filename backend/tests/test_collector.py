import logging
from datetime import UTC, datetime, timedelta

from app.market import collector, service


def test_한건이_실패해도_나머지는_계속_수집한다(monkeypatch):
    """[실패 격리 테스트] 업비트 요청 한 건이 에러가 나도, 나머지 5건은 정상 수집되는지 확인한다.
    업비트가 가끔 에러(429 등)를 줘도 15분 수집 전체가 멈추면 안 되기 때문에 필요하다.
    실제 업비트와 DB를 쓰지 않고 fetch_candles/save_candles를 가짜로 바꿔서 검사한다.
    """
    attempted = []  # 수집을 시도한 (코인,봉) 기록
    saved = []  # 저장까지 간 (코인,봉) 기록

    def fake_fetch(market, timeframe, count, to=None):
        attempted.append((market, timeframe))
        if (market, timeframe) == ("KRW-BTC", "1h"):
            raise RuntimeError("업비트 장애 흉내")  # 이 한 건만 일부러 실패
        return [{"market": market}]  # 저장 함수가 누구 것인지 알 수 있게 market만

    def fake_save(db, timeframe, raw_candles):
        saved.append((raw_candles[0]["market"], timeframe))
        return len(raw_candles)

    # monkeypatch.setattr(대상, "이름", 새값): 테스트 동안만 그 이름을 가짜로 바꾼다 (끝나면 자동 복구).
    monkeypatch.setattr(service, "fetch_candles", fake_fetch)
    monkeypatch.setattr(service, "save_candles", fake_save)
    monkeypatch.setattr(
        collector, "_warn_recent_gaps", lambda db: None
    )  # 결측 검사는 DB가 필요해서 건너뜀
    monkeypatch.setattr(
        collector, "SLEEP_SECONDS", 0
    )  # 테스트가 느려지지 않게 대기 시간을 없앤다

    collector.collect_latest()

    assert len(attempted) == 6  # 2코인 x 3봉 = 6건을 전부 시도했다
    assert len(saved) == 5  # 실패한 1건을 뺀 5건이 저장됐다
    assert ("KRW-BTC", "1h") not in saved  # 실패한 건은 저장되지 않았다


def test_최근_결측만_경고한다(monkeypatch, caplog):
    """[결측 경고 테스트] 최근 7일 안의 결측은 경고 로그를 남기고, 오래된 결측은 조용히 넘어가는지 확인한다.
    업비트 원본에 영구히 없는 과거 결측을 15분마다 반복해서 경고하지 않기 위한 규칙이다.
    find_gaps를 가짜로 바꿔서 '결측이 이렇게 있다'고 가정한다 (DB 불필요).
    """
    now = datetime.now(UTC)
    recent = (
        now - timedelta(days=2, hours=8),
        now - timedelta(days=2),
    )  # 2일 전: 최근
    old = (
        now - timedelta(days=30, hours=8),
        now - timedelta(days=30),
    )  # 30일 전: 오래됨

    monkeypatch.setattr(collector, "MARKETS", ["KRW-BTC"])
    monkeypatch.setattr(collector, "GAP_CHECK_TIMEFRAMES", ["4h"])
    # lambda: 이름 없는 한 줄 함수 (자바 람다 (db, m, t) -> List.of(old, recent) 와 같다)
    monkeypatch.setattr(
        collector, "find_gaps", lambda db, market, timeframe: [old, recent]
    )

    # caplog: 테스트 중 남은 로그를 모아서 보여 주는 pytest 도구
    with caplog.at_level(logging.WARNING):
        collector._warn_recent_gaps(
            None
        )  # find_gaps가 가짜라 db는 쓰이지 않아 None을 넘긴다

    assert len(caplog.records) == 1  # 최근 1건만 경고했고 오래된 건 무시했다
    assert "KRW-BTC" in caplog.text


def test_복구는_며칠_전_자정부터_6건을_받는다(monkeypatch):
    """[복구 범위 테스트] 서버 시작 시 복구가 '3일 전 자정(UTC)'부터, 2코인 x 3봉 = 6건을 받는지 확인한다.
    자정에 맞추지 않으면 일봉이나 4시간봉의 시작 경계가 잘려 캔들이 빠질 수 있다.
    """
    starts = []  # backfill이 받은 시작 시각 기록

    def fake_backfill(db, market, timeframe, start):
        starts.append(start)

    monkeypatch.setattr(collector, "backfill", fake_backfill)
    monkeypatch.setattr(collector, "SLEEP_SECONDS", 0)

    collector.recover_recent()

    assert len(starts) == 6
    start = starts[0]
    assert (start.hour, start.minute, start.second) == (0, 0, 0)  # 자정이다
    age = datetime.now(UTC) - start
    assert timedelta(days=3) <= age < timedelta(days=4)  # 3일 전 자정이다
