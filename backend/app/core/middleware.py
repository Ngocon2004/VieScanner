"""HTTP middleware: gắn `request_id` và log mỗi request."""

from __future__ import annotations

import re
import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.error_handlers import error_response
from app.core.exceptions import RequestTooLargeError
from app.core.logging import logger


REQUEST_ID_HEADER = "X-Request-ID"
# request_id được ghi vào log và cột `scans.request_id` (String(36)); giá trị lạ từ client
# có thể chèn dòng log giả hoặc làm insert scan thất bại -> chỉ nhận chuỗi an toàn.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,36}$")


def _resolve_request_id(raw: str | None) -> str:
    if raw and _SAFE_REQUEST_ID.match(raw):
        return raw
    return str(uuid.uuid4())


def _declared_length(request: Request) -> int:
    raw = request.headers.get("content-length", "")
    return int(raw) if raw.isdigit() else 0


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gắn UUID cho mỗi request và log start/finish + duration.

    - Đọc `X-Request-ID` từ client (nếu có) để hỗ trợ trace xuyên service,
      ngược lại tự sinh UUID4.
    - Inject vào `request.state.request_id` để handler/exception handler đọc lại.
    - Trả về cùng header để client correlation.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id

        # contextualize (contextvar) thay vì bind: log trong handler/thread OCR cũng mang request_id,
        # nhờ đó lần theo được lỗi từ request_id người dùng báo lại.
        with logger.contextualize(request_id=request_id):
            start = time.perf_counter()
            logger.info("→ {method} {path}", method=request.method, path=request.url.path)

            try:
                if _declared_length(request) > settings.max_request_bytes:
                    # Chặn trước khi nhận body. RequestBodyLimitMiddleware của Starlette cũng chặn nhưng
                    # thay phản hồi bằng chữ thuần "Content Too Large" mà giao diện không đọc được.
                    response = error_response(RequestTooLargeError(), request_id)
                else:
                    response = await call_next(request)
            except Exception:
                # Re-raise – exception handler ở app level sẽ format response.
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.exception(
                    "✗ {method} {path} crashed in {elapsed:.1f}ms",
                    method=request.method,
                    path=request.url.path,
                    elapsed=elapsed_ms,
                )
                raise

            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "← {method} {path} {status} {elapsed:.1f}ms",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                elapsed=elapsed_ms,
            )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["RequestContextMiddleware", "REQUEST_ID_HEADER"]
