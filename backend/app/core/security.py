import secrets
from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

# 요청 헤더 "X-API-Key"에서 값을 꺼내는 도구.
# auto_error=False: 헤더가 없을 때 FastAPI 기본 에러 대신 None을 주게 한다.
#                   그래야 아래에서 우리 공통 에러 형식(UnauthorizedError)으로 응답할 수 있다.
# 이걸 쓰면 Swagger 화면(/docs)에 "Authorize" 버튼이 생겨서 키를 넣고 바로 테스트할 수 있다.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_internal_key(
    api_key: Annotated[str | None, Security(api_key_header)],
) -> None:
    """internal API 입구 검사. 라우터에 Depends로 붙이면 요청마다 핸들러보다 먼저 실행된다.
    스프링의 HandlerInterceptor.preHandle()과 같은 역할이다.
    통과하면 아무것도 안 하고, 실패하면 UnauthorizedError를 던진다.
    """
    # compare_digest: 문자열을 항상 같은 시간에 비교한다.
    # 일반 == 비교는 틀린 글자를 만나면 바로 끝나서, 응답 시간 차이로 키를 추측하는 공격(타이밍 공격)에 약하다.
    # compare_digest는 문자열이 아닌 bytes로 비교해야 한글 등이 섞여도 에러가 안 난다.
    if api_key is None or not secrets.compare_digest(
        api_key.encode(), settings.internal_api_key.encode()
    ):
        raise UnauthorizedError("유효하지 않은 API키 입니다")
