from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logger import exception_group_key, format_exception_struct, get_logger

BAD_REQUEST_MESSAGE = "잘못된 유형의 요청"
NOT_FOUND_MESSAGE = "요청 또는 자원을 찾을 수 없음."
INTERNAL_ERROR_MESSAGE = "내부 서버 오류"


class AppException(Exception):
    def __init__(
        self,
        message: str = INTERNAL_ERROR_MESSAGE,
        http_status: int = 500,
        level: str = "ERROR",
        **additional_args: Any,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.level = level
        self.additional_args = additional_args

    def to_json_response(self) -> JSONResponse:
        try:
            status_phrase = HTTPStatus(self.http_status).phrase
            http_status_str = f"{self.http_status} {status_phrase}"
        except ValueError:
            http_status_str = str(self.http_status)
        return JSONResponse(
            status_code=self.http_status,
            content={"message": self.message, "http_status": http_status_str},
        )


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    try:
        first_error = exc.errors()[0]
        field = first_error.get("loc", ["unknown"])[-1]
        msg = first_error.get("msg", "Field Error")
    except (IndexError, TypeError, AttributeError):
        field = "unknown"
        msg = "잘못된 입력 포맷입니다."

    error_message = f"[{field}]: {msg}"
    client_addr = request.client.host if request.client else "unknown"
    request_line = f"{request.method} {request.url.path}"

    get_logger().error(
        error_message,
        status_code=400,
        request_line=request_line,
        client_addr=client_addr,
        detail=exc.errors(),
    )
    return AppException(message=error_message, http_status=400).to_json_response()


async def _app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    client_addr = request.client.host if request.client else "unknown"
    request_line = f"{request.method} {request.url.path}"
    log_kwargs = {
        "status_code": exc.http_status,
        "request_line": request_line,
        "client_addr": client_addr,
        **exc.additional_args,
    }
    if exc.level == "ERROR":
        get_logger().error(exc.message, **log_kwargs)
    else:
        get_logger().warning(exc.message, **log_kwargs)
    return exc.to_json_response()


async def _generic_exception_handler(request: Request, e: Exception) -> JSONResponse:
    client_addr = request.client.host if request.client else "unknown"
    request_line = f"{request.method} {request.url.path}"

    ex = format_exception_struct(e)
    group = exception_group_key(ex["type"], ex["frames"])
    summary = ex["frames"][-3:] if ex["frames"] else []

    get_logger().error(
        INTERNAL_ERROR_MESSAGE,
        status_code=500,
        client_addr=client_addr,
        request_line=request_line,
        detail=summary,
        error_type=ex["type"],
        error_message=ex["message"],
        error_group=group,
        error_frames=ex["frames"],
    )
    return AppException(message=INTERNAL_ERROR_MESSAGE, http_status=500).to_json_response()


def global_exception_advice(app) -> None:
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(AppException, _app_exception_handler)
    app.add_exception_handler(Exception, _generic_exception_handler)
