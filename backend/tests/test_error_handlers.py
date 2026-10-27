from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.exceptions import AppError
from app.main import app

# 테스트 전용 임시 URL 3개를 앱에 붙인다. 실제 서비스 API로는 에러를 일부러 낼 방법이 없어서 이렇게 만든다.
# 자바에서 테스트용 @RestController를 따로 만들어 예외 처리를 검사하는 것과 같다.
demo_router = APIRouter()


@demo_router.get("/_test/app-error")
def raise_app_error():
    # 기본 AppError는 상태 코드 400, 코드 BAD_REQUEST다.
    raise AppError("테스트용 에러")


@demo_router.get("/_test/boom")
def raise_unexpected():
    # 우리가 정의하지 않은 일반 에러. 500으로 바뀌어야 한다.
    raise RuntimeError("내부 비밀 정보")


@demo_router.get("/_test/number/{n}")
def number(n: int):
    # n이 숫자가 아니면 FastAPI가 자동으로 검증 오류를 낸다.
    return n


app.include_router(demo_router)

# raise_server_exceptions=False: 서버가 에러를 던져도 테스트 도구가 같이 터지지 않고 500 응답을 돌려준다.
# 이걸 안 쓰면 500 응답을 검사할 수 없다 (기본값은 에러를 그대로 테스트에 터뜨린다).
client = TestClient(app, raise_server_exceptions=False)


def test_AppError는_상태코드와_코드를_공통_모양으로_응답한다():
    response = client.get("/_test/app-error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "BAD_REQUEST", "message": "테스트용 에러"}
    }


def test_요청값이_잘못되면_422와_공통_모양으로_응답한다():
    response = client.get("/_test/number/abc")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_예상_못한_에러는_500이고_내부_내용을_숨긴다():
    response = client.get("/_test/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    # 에러 메시지("내부 비밀 정보")가 응답에 새면 안 된다.
    assert "내부 비밀 정보" not in response.text
