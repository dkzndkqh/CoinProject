import pytest
from fastapi.testclient import TestClient

from app.agent import service as agent_service
from app.core.db import get_db
from app.core.exceptions import AnalysisUnavailableError, NotFoundError
from app.main import app
from tests.test_agent_scenario import FOUR, ONE, make_data

# TestClient: 서버를 띄우지 않고 메모리에서 HTTP 요청을 보낸다 (자바 MockMvc와 같은 역할).
# with 없이 쓰는 이유: lifespan(스케줄러, 캔들 복구)이 실행되면 외부 API를 부르기 때문이다.
client = TestClient(app)


def fake_get_db():
    # service.analyze까지 가짜로 바꾸므로 DB 세션은 쓰이지 않는다.
    yield None


app.dependency_overrides[get_db] = fake_get_db

URL = "/api/agent/analyze"
BODY = {"market": "KRW-BTC", "question": "3일 뒤 어때?"}


def fake_result(scenario):
    """service.analyze()가 돌려주는 dict와 같은 모양."""
    return {
        "kind": "analysis",
        "market": "KRW-BTC",
        "stance": "관망",
        "horizon": "3d",
        "message": "지금은 방향이 뚜렷하지 않아 관망을 권합니다.",
        "price": 100000000.0,
        "price_time_kst": "2026-11-02 12:00 KST",
        "scenario": scenario,
        "disclaimer": agent_service.DISCLAIMER,
    }


def test_정상_요청이면_200과_시나리오가_담긴_응답을_준다(monkeypatch):
    scenario = agent_service.build_scenario(make_data(FOUR, ONE), "3d")
    monkeypatch.setattr(
        agent_service, "analyze", lambda db, body: fake_result(scenario)
    )

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["stance"] == "관망"
    assert body["disclaimer"] == agent_service.DISCLAIMER
    assert body["scenario"]["input"] == "1d"
    assert [p["horizon"] for p in body["scenario"]["points"]] == ["1d", "2d", "3d"]


def test_시나리오가_없으면_scenario는_null이다(monkeypatch):
    monkeypatch.setattr(agent_service, "analyze", lambda db, body: fake_result(None))

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert response.json()["scenario"] is None


def test_요청_본문이_서비스에_통째로_넘어간다(monkeypatch):
    received = {}

    def fake(db, body):
        received["body"] = body
        return fake_result(None)

    monkeypatch.setattr(agent_service, "analyze", fake)

    # 질문 앞뒤 공백은 스키마에서 잘려서 넘어간다
    client.post(
        URL,
        json={
            "market": "KRW-ETH",
            "question": "  일주일 뒤는?  ",
            "horizon": "7d",
            "history": [{"role": "user", "content": "ETH 어때?"}],
        },
    )

    body = received["body"]
    assert (body.market, body.question, body.horizon) == (
        "KRW-ETH",
        "일주일 뒤는?",
        "7d",
    )
    assert [(t.role, t.content) for t in body.history] == [("user", "ETH 어때?")]


def test_거절이면_200과_kind_reject_응답을_준다(monkeypatch):
    reject = {"kind": "reject", "message": agent_service.REJECT_MESSAGE}
    monkeypatch.setattr(agent_service, "analyze", lambda db, body: reject)

    response = client.post(URL, json=BODY)

    assert response.status_code == 200
    assert response.json() == reject


@pytest.mark.parametrize(
    "body",
    [
        {"market": "KRW-SOL", "question": "어때?"},  # 지원하지 않는 코인
        {"market": "KRW-BTC", "question": ""},  # 빈 질문
        {"market": "KRW-BTC", "question": "   "},  # 공백만
        {"market": "KRW-BTC", "question": "가" * 501},  # 너무 긴 질문
        {"market": "KRW-BTC", "question": "어때?", "horizon": "내일"},  # 기간 형식 오류
        {
            "question": "어때?",
            "history": [{"role": "user", "content": "a"}] * 7,
        },  # 이력 7개 (상한 6)
        {"market": "KRW-BTC"},  # 질문 칸 없음
        {},  # 본문이 비어 있음
    ],
)
def test_잘못된_요청은_서비스에_가기_전에_422(monkeypatch, body):
    def must_not_call(db, body):
        raise AssertionError(
            "잘못된 요청인데 service가 호출됨 (Claude 비용이 나갈 수 있다)"
        )

    monkeypatch.setattr(agent_service, "analyze", must_not_call)

    response = client.post(URL, json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_시장_데이터가_없으면_404(monkeypatch):
    def fake(db, body):
        raise NotFoundError("분석에 필요한 시장 데이터가 아직 준비되지 않았습니다")

    monkeypatch.setattr(agent_service, "analyze", fake)

    response = client.post(URL, json=BODY)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_분석을_못_만들면_503(monkeypatch):
    def fake(db, body):
        raise AnalysisUnavailableError(agent_service.UNAVAILABLE_MESSAGE)

    monkeypatch.setattr(agent_service, "analyze", fake)

    response = client.post(URL, json=BODY)

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "ANALYSIS_UNAVAILABLE"
    assert error["message"] == agent_service.UNAVAILABLE_MESSAGE
