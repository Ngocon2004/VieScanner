"""Exception handlers táº­p trung cho FastAPI app.

Má»i exception (Ä‘Ã£ biáº¿t hoáº·c khÃ´ng) Ä‘Æ°á»£c chuyá»ƒn thÃ nh response JSON nháº¥t quÃ¡n:

    {
        "code": "image_invalid",       // mÃ£ lá»—i machine-readable
        "message": "..."                // thÃ´ng Ä‘iá»‡p tiáº¿ng Viá»‡t cho user
        "request_id": "uuid"            // dÃ¹ng Ä‘á»ƒ khá»›p vá»›i log server
    }
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import VieScannerError
from app.core.logging import logger


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


async def _viescanner_error_handler(request: Request, exc: VieScannerError) -> JSONResponse:
    rid = _request_id(request)
    logger.bind(request_id=rid).warning(
        "{code}: {message}", code=exc.code, message=exc.message
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "request_id": rid},
    )


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    rid = _request_id(request)
    # `exc.errors()` cÃ³ thá»ƒ chá»©a ValueError/ctx khÃ´ng JSON-serializable;
    # `jsonable_encoder` xá»­ lÃ½ cÃ¡c kiá»ƒu nÃ y thÃ nh chuá»—i.
    safe_errors = jsonable_encoder(exc.errors())
    logger.bind(request_id=rid).warning(
        "validation_error: {errors}", errors=safe_errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "code": "validation_error",
            "message": "Dá»¯ liá»‡u Ä‘áº§u vÃ o khÃ´ng há»£p lá»‡.",
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
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": "http_error",
            "message": str(exc.detail),
            "request_id": rid,
        },
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id(request)
    logger.bind(request_id=rid).exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "internal_error",
            "message": "CÃ³ lá»—i há»‡ thá»‘ng. Vui lÃ²ng thá»­ láº¡i sau.",
            "request_id": rid,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """ÄÄƒng kÃ½ toÃ n bá»™ handler vÃ o FastAPI app."""
    app.add_exception_handler(VieScannerError, _viescanner_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)


__all__ = ["register_exception_handlers"]

