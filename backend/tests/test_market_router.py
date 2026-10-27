from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.market import service

# TestClient: 서버를 띄우지 않고 메모리 안에서 HTTP 요청을 보내는 도구다.
# 자바 Spring의 MockMvc와 같은 역할이다 (mockMvc.perform(get("/...")) <-> client.get("/...")).
# 주의: `with TestClient(app)` 으로 쓰지 않으면 lifespan(스케줄러, 백필 복구)이 실행되지 않는다.
#       테스트에서는 외부 API를 부르면 안 되므로 일부러 with 없이 쓴다.
client = TestClient(app)


def fake_get_db():
    """진짜 DB 대신 쓸 가짜 세션 공급 함수.
    service 함수까지 monkeypatch로 바꿔치기하므로 db 객체는 실제로 쓰이지 않는다. None이면 충분하다."""
    yield None


# 의존성 오버라이드: FastAPI가 Depends(get_db)를 부를 때 fake_get_db를 대신 부르게 한다.
# 자바 Spring 테스트에서 @MockBean으로 빈을 갈아끼우는 것과 비슷하다.
app.dependency_overrides[get_db] = fake_get_db


def test_정상_코인이면_200과_판정_dict를_돌려준다(monkeypatch):
    # monkeypatch: 테스트 동안만 객체의 속성을 바꾸고, 끝나면 자동으로 되돌리는 pytest 도구다.
    # service.get_indicator_judgement를 가짜 함수로 바꿔서 DB 없이 라우터만 검사한다.
    # (Mockito의 when(service.xxx()).thenReturn(...) 과 같다.)

    fake_result = {"market": "KRW-BTC", "4h": {}, "1d": {}}
    monkeypatch.setattr(
        service, "get_indicator_judgement", lambda db, market: fake_result
    )

    response = client.get("/api/market/btc/indicators")

    assert response.status_code == 200
    assert response.json() == fake_result


def test_코인_이름은_대소문자를_구분하지_않는다(monkeypatch):
    # 라우터가 서비스에 넘긴 market 값을 기록해서, "ETH"가 "KRW-ETH"로 바뀌는지 확인
    received = {}

    def fake(db, market):
        received["market"] = (
            market  # 넘어온 인자를 dict에 기록 ( Mockito의 verify/ArgumentCaptor 역할)
        )
        return {"market": market}

    monkeypatch.setattr(service, "get_indicator_judgement", fake)

    response = client.get("/api/market/ETH/indicators")

    assert response.status_code == 200
    assert received["market"] == "KRW-ETH"


def test_지원하지_않는_코인이면_404(monkeypatch):
    # 입구에서 막히므로 service는 아예 호출되면 안 된다. 호출되면 즉시 실패하게 만든다.
    def must_not_call(db, market):
        raise AssertionError("지원하지 않는 코인인데 service가 호출됨")

    monkeypatch.setattr(service, "get_indicator_judgement", must_not_call)

    response = client.get("/api/market/doge/indicators")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_캔들_데이터가_없으면_404(monkeypatch):
    # service가 None을 돌려주는 경우(캔들 부족)를 흉내 낸다.
    monkeypatch.setattr(service, "get_indicator_judgement", lambda db, market: None)

    response = client.get("/api/market/btc/indicators")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
