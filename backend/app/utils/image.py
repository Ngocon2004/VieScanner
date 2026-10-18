"""Tiện ích nhận và validate file ảnh upload."""

from __future__ import annotations

import os

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import ImageValidationError


__all__ = [
    "ImageValidationError",
    "detect_image_mime",
    "read_upload_limited",
    "safe_upload_filename",
    "validate_image_bytes",
]

_MAX_FILENAME_LEN = 255


def detect_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def read_upload_limited(file: UploadFile) -> bytes:
    # Đọc tối đa giới hạn + 1 byte: file quá lớn bị chặn mà không phải nạp hết vào RAM.
    data = await file.read(settings.max_upload_size_bytes + 1)
    if len(data) > settings.max_upload_size_bytes:
        raise ImageValidationError(
            f"Kích thước file vượt quá {settings.max_upload_size_mb}MB."
        )
    return data


def safe_upload_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    name = os.path.basename(filename.replace("\\", "/")).strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return name[-_MAX_FILENAME_LEN:] or None


def validate_image_bytes(content_type: str | None, data: bytes) -> str:
    """Trả về MIME thật của ảnh, xác định từ magic bytes.

    Không tin `Content-Type` do client khai báo (trình duyệt/kéo-thả có thể gửi rỗng
    hoặc sai); quyết định dựa trên nội dung file và danh sách `ALLOWED_MIME_TYPES_RAW`.
    """
    if not data:
        raise ImageValidationError("File ảnh rỗng.")

    if len(data) > settings.max_upload_size_bytes:
        raise ImageValidationError(
            f"Kích thước file vượt quá {settings.max_upload_size_mb}MB."
        )

    detected = detect_image_mime(data)
    if detected is None or detected not in settings.allowed_mime_types:
        allowed = ", ".join(settings.allowed_mime_types)
        raise ImageValidationError(
            f"Loại file '{content_type or 'unknown'}' không được hỗ trợ. Chỉ chấp nhận: {allowed}."
        )
    return detected
