from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.exceptions import ImageValidationError
from app.utils.image import validate_image_bytes


def test_validate_image_bytes_accepts_png_signature() -> None:
    data = b"\x89PNG\r\n\x1a\nrest-of-bytes"
    mime = validate_image_bytes("image/png", data)
    assert mime == "image/png"


def test_validate_image_bytes_rejects_empty_payload() -> None:
    with pytest.raises(ImageValidationError):
        validate_image_bytes("image/png", b"")


def test_validate_image_bytes_rejects_unsupported_mime() -> None:
    with pytest.raises(ImageValidationError):
        validate_image_bytes("text/plain", b"hello")


def test_validate_image_bytes_rejects_mime_magic_mismatch() -> None:
    jpeg_like = b"\xff\xd8\xff\xdbrest"
    with pytest.raises(ImageValidationError):
        validate_image_bytes("image/png", jpeg_like)


def test_validate_image_bytes_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    oversized = b"\x89PNG\r\n\x1a\n" + (b"a" * (1024 * 1024 + 1))

    with pytest.raises(ImageValidationError):
        validate_image_bytes("image/png", oversized)


def test_validate_image_bytes_accepts_valid_webp_header() -> None:
    # Minimal RIFF + WEBP marker; validator only checks magic bytes.
    data = b"RIFF\x24\x00\x00\x00WEBPVP8 "
    mime = validate_image_bytes("image/webp", data)
    assert mime == "image/webp"
