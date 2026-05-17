"""Cấu hình logging tập trung dùng `loguru`.

Đặc điểm:
- Output JSON-ish có timestamp, level, module → dễ ingest sang ELK/Loki.
- Tự động bind `request_id` (UUID4) cho mỗi request HTTP qua middleware.
- Tự động flush trên uncaught exception.

Cách dùng:

    from app.core.logging import logger
    logger.info("Started OCR", file_size=len(data))

Trong handler/middleware, dùng `logger.bind(request_id=...)` để gắn context.
"""

from __future__ import annotations

import sys
from typing import Any

from loguru import logger

from app.core.config import settings


def _format_record(record: dict[str, Any]) -> str:
    """Format log theo dạng có request_id (nếu có).

    Tránh dùng JSON sink mặc định để dev đọc cho dễ; ở prod có thể chuyển sang
    JSON với `serialize=True`.
    """
    extra = record["extra"]
    rid = extra.get("request_id", "-")
    record["extra"]["rid"] = rid
    # Backslashes trong path Windows dễ gây nhầm format; dùng | làm separator.
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>rid={extra[rid]}</cyan> | "
        "<cyan>{name}:{function}:{line}</cyan> | "
        "<level>{message}</level>\n"
    )


def configure_logging() -> None:
    """Khởi tạo logger; gọi 1 lần ở module main."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if settings.debug else "INFO",
        format=_format_record,
        backtrace=True,
        diagnose=settings.debug,  # diagnose=False ở prod để tránh leak PII trong traceback
        enqueue=False,
    )

    logger.info(
        "Logging configured | debug={} | app={} v{}",
        settings.debug,
        settings.app_name,
        settings.app_version,
    )


__all__ = ["logger", "configure_logging"]
