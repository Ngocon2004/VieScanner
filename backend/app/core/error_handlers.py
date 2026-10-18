"""Exception handlers tập trung cho FastAPI app.

Mọi exception (đã biết hoặc không) được chuyển thành response JSON nhất quán:

    {
        "code": "image_invalid",       // mã lỗi machine-readable
        "message": "..."                // thông điệp tiếng Việt cho user
        "request_id": "uuid"            // dùng để khớp với log server
    }
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import RequestTooLargeError, VieScannerError
from app.core.logging import logger


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_response(exc: VieScannerError, request_id: str) -> JSONResponse:
    content: dict = {"code": exc.code, "message": exc.message, "request_id": request_id}
    details = getattr(exc, "details", None)
    if details:
        content["details"] = jsonable_encoder(details)
    return JSONResponse(status_code=exc.status_code, content=content)


async def _viescanner_error_handler(request: Request, exc: VieScannerError) -> JSONResponse:
    rid = _request_id(request)
    logger.bind(request_id=rid).warning(
        "{code}: {message}", code=exc.code, message=exc.message
    )
    return error_response(exc, rid)


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    rid = _request_id(request)
    # `exc.errors()` có thể chứa ValueError/ctx không JSON-serializable;
    # `jsonable_encoder` xử lý các kiểu này thành chuỗi.
    safe_errors = jsonable_encoder(exc.errors())
    logger.bind(request_id=rid).warning(
        "validation_error: {errors}", errors=safe_errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "code": "validation_error",
            "message": "Dữ liệu đầu vào không hợp lệ.",
            "details": safe_errors,
            "request_id": rid,
        },
    )


async def _http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    rid = _request_id(request)
    logger.bind(request_id=rid).warning(
        "http_error: status={status} detail={detail}",
        status=exc.status_code,
        detail=exc.detail,
    )
    # Body gửi kiểu chunked (không khai báo độ dài) vượt giới hạn: RequestBodyLimitMiddleware raise 413.
    if exc.status_code == status.HTTP_413_CONTENT_TOO_LARGE:
        return error_response(RequestTooLargeError(), rid)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "http_error", "message": str(exc.detail), "request_id": rid},
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id(request)
    logger.bind(request_id=rid).exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "internal_error",
            "message": "Có lỗi hệ thống. Vui lòng thử lại sau.",
            "request_id": rid,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Đăng ký toàn bộ handler vào FastAPI app."""
    app.add_exception_handler(VieScannerError, _viescanner_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)


__all__ = ["register_exception_handlers"]

