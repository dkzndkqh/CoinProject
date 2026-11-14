from fastapi.testclient import TestClient

from app.main import app

# with 없이 만들어서 lifespan(스케줄러, 백필 복구)이 실행되지 않게 한다. 외부 API를 부르면 안 되기 때문이다.
# CORS 미들웨어는 라우터에 닿기 전에 동작하므로 DB 없이 /openapi.json 같은 가벼운 경로로 충분히 검사된다.
client = TestClient(app)

# 설정 기본값(cors_origins)에 들어 있는 Vite 개발 서버 주소
ALLOWED = "http://localhost:5173"


def test_허용한_출처면_허용_헤더가_붙는다():
    # 브라우저는 요청에 Origin 헤더를 자동으로 붙인다. 허용 목록에 있으면 서버가 같은 값을 돌려준다.
    res = client.get("/openapi.json", headers={"Origin": ALLOWED})

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED


def test_허용하지_않은_출처면_허용_헤더가_없다():
    # 헤더가 없으면 브라우저가 응답을 JS에 넘기지 않고 막는다. (서버가 요청을 거부하는 게 아니라 브라우저가 막는다.)
    res = client.get("/openapi.json", headers={"Origin": "http://evil.com"})

    assert "access-control-allow-origin" not in res.headers


def test_POST_사전요청이_허용된다():
    # JSON을 POST로 보내기 전에 브라우저가 먼저 OPTIONS(사전 요청, preflight)로 "보내도 되나?" 하고 묻는다.
    res = client.options(
        "/api/agent/analyze",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in res.headers["access-control-allow-methods"]
