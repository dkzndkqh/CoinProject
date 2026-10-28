# 앱 전체에서 쓰는 에러 클래스 모음.
# 서비스와 라우터는 HTTP를 몰라도 되게, 이 에러만 던진다 (raise).
# 던져진 에러를 HTTP 응답(상태 코드 + JSON)으로 바꾸는 일은 main.py의 전역 핸들러가 한다.


class AppError(Exception):
    """우리 앱의 모든 에러의 부모 클래스.
    자바에서 `class AppException extends RuntimeException`을 만드는 것과 같다.
    """

    status_code: int = 400  # HTTP 상태 코드
    code: str = "BAD_REQUEST"

    def __init__(self, message: str):
        # super().__init__(message): 부모 (Exception) 생성자에 메세지를 넘긴다.
        # 자바의 super(message)와 같다.
        super().__init__(message)
        self.message = message  # 응답에 담을 사람이 읽는 설명


class NotFoundError(AppError):
    """찾는 대상이 없을 때 (404). 예: 지원하지 않는 코인, 데이터 없음."""

    status_code = 404
    code = "NOT_FOUND"


class UnauthorizedError(AppError):
    """인증 실패 (401). 예: internal API 키가 없거나 틀림."""

    status_code = 401
    code = "UNAUTHORIZED"
