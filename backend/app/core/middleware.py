"""HTTP middleware: gắn `request_id` và log mỗi request."""

from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import logger


REQUEST_ID_HEADER = "X-Request-ID"


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
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        bound = logger.bind(request_id=request_id)
        start = time.perf_counter()
        bound.info("→ {method} {path}", method=request.method, path=request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            # Re-raise – exception handler ở app level sẽ format response.
            elapsed_ms = (time.perf_counter() - start) * 1000
            bound.exception(
                "✗ {method} {path} crashed in {elapsed:.1f}ms",
                method=request.method,
                path=request.url.path,
                elapsed=elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        bound.info(
            "← {method} {path} {status} {elapsed:.1f}ms",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed=elapsed_ms,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["RequestContextMiddleware", "REQUEST_ID_HEADER"]
