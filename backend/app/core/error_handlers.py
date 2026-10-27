import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError

# 이 파일 전용 로거. 자바의 LoggerFactory.getLogger(Xxx.class)
logger = logging.getLogger(__name__)


def error_body(code: str, message: str) -> dict:
    """모든 에러 응답이 따르는 공통 모양. {"error": {"code": ..., "message": ...}}"""
    return {"error": {"code": code, "message": message}}


# async def: FastAPI가 비동기로 부르는 함수 형태 핸들러는 이 모양으로 쓰는 것이 약속이다.
# 자바 @ExceptionHandler 메서드에 (예외, 요청)이 들어오는 것과 같다.


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """우리가 던진 AppError(NotFoundError 등 자식 포함)를 상태 코드와 JSON으로 바꾼다."""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
    )


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """요청 값이 잘못됐을 때 (FastAPI가 자동으로 검사하다 실패한 경우) 422로 응답한다.
    FastAPI 기본 응답({"detail": [...]})을 우리 공통 모양으로 통일한다.
    """
    # 자세한 오류 목록(exc.errors())은 응답에 그대로 내보내지 않고 로그에만 남긴다.
    logger.info("요청 값 검증 실패: %s %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content=error_body("VALIDATION_ERROR", "요청 값이 올바르지 않습니다"),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """예상하지 못한 모든 에러. 스택 트레이스(내부 정보)를 응답에 노출하지 않고 로그에만 남긴다."""
    logger.exception("처리되지 않은 에러: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "서버 오류가 발생했습니다"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """위 핸들러 3개를 앱에 등록한다. main.py에서 한 번 호출한다.
    첫 인자가 '잡을 에러 종류', 두 번째가 '처리 함수'다.
    AppError를 등록하면 그 자식(NotFoundError 등)도 자동으로 같이 처리된다 (상속).
    """

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
