"""Tiện ích tạo Content-Disposition header an toàn."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _ascii_fallback(value: str) -> str:
    """Chuyển chuỗi (có thể chứa unicode) sang dạng ASCII-safe."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    safe = _UNSAFE_CHARS.sub("_", ascii_only).strip("._-")
    return safe or "file"


def build_content_disposition(filename: str) -> str:
    """Build Content-Disposition header theo RFC 5987.

    Cho phép tên tiếng Việt qua `filename*=UTF-8''...`, đồng thời có fallback ASCII.
    Tự động chặn ký tự CR/LF (header injection).
    """
    # Loại bỏ CR/LF để chặn header injection
    cleaned = filename.replace("\r", "").replace("\n", "").strip()
    if not cleaned:
        cleaned = "file"

    ascii_name = _ascii_fallback(cleaned)
    utf8_name = quote(cleaned, safe="")

    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
