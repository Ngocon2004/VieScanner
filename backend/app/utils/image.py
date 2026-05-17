"""Tiện ích validate file ảnh upload.

Kiểm tra:
- Kích thước (so với `settings.max_upload_size_bytes`).
- MIME type theo header `Content-Type`.
- Magic bytes thực tế trong nội dung file (tránh giả mạo extension/MIME).
"""

from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import ImageValidationError


# Mapping: MIME type được phép -> tuple các signature (magic bytes) hợp lệ.
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    # WEBP: "RIFF????WEBP" – ta check prefix RIFF và chuỗi WEBP ở offset 8.
    "image/webp": (b"RIFF",),
}


__all__ = ["ImageValidationError", "validate_image_bytes"]


def validate_image_bytes(content_type: str | None, data: bytes) -> str:
    """Validate ảnh upload.

    Trả về MIME type đã được xác nhận. Raise `ImageValidationError` nếu không hợp lệ.
    """
    if not data:
        raise ImageValidationError("File ảnh rỗng.")

    if len(data) > settings.max_upload_size_bytes:
        raise ImageValidationError(
            f"Kích thước file vượt quá {settings.max_upload_size_mb}MB."
        )

    if not content_type or content_type not in settings.allowed_mime_types:
        allowed = ", ".join(settings.allowed_mime_types)
        raise ImageValidationError(
            f"Loại file '{content_type or 'unknown'}' không được hỗ trợ. Chỉ chấp nhận: {allowed}."
        )

    signatures = _MAGIC_BYTES.get(content_type, ())
    if not any(data.startswith(sig) for sig in signatures):
        raise ImageValidationError("Nội dung file không khớp với loại ảnh khai báo.")

    # WEBP cần check thêm chuỗi 'WEBP' ở offset 8
    if content_type == "image/webp" and (len(data) < 12 or data[8:12] != b"WEBP"):
        raise ImageValidationError("File WEBP không hợp lệ.")

    return content_type
