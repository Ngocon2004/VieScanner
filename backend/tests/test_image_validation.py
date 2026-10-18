from __future__ import annotations

import io

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import ImageValidationError
from app.utils.image import read_upload_limited, safe_upload_filename, validate_image_bytes


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


def test_validate_image_bytes_trusts_content_over_declared_mime() -> None:
    jpeg_like = b"\xff\xd8\xff\xdbrest"
    assert validate_image_bytes("image/png", jpeg_like) == "image/jpeg"
    assert validate_image_bytes("application/octet-stream", jpeg_like) == "image/jpeg"
    assert validate_image_bytes(None, b"\x89PNG\r\n\x1a\nrest") == "image/png"


def test_validate_image_bytes_rejects_image_declared_but_not_image_content() -> None:
    with pytest.raises(ImageValidationError):
        validate_image_bytes("image/png", b"GIF89a-not-allowed")


def test_validate_image_bytes_respects_allowed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "allowed_mime_types_raw", "image/jpeg")
    with pytest.raises(ImageValidationError):
        validate_image_bytes("image/png", b"\x89PNG\r\n\x1a\nrest")


def test_validate_image_bytes_rejects_riff_that_is_not_webp() -> None:
    with pytest.raises(ImageValidationError):
        validate_image_bytes("image/webp", b"RIFF\x24\x00\x00\x00WAVEfmt ")


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


def test_safe_upload_filename_strips_paths_and_limits_length() -> None:
    assert safe_upload_filename(None) is None
    assert safe_upload_filename(r"C:\Users\a\front.jpg") == "front.jpg"
    assert safe_upload_filename("../../etc/passwd") == "passwd"
    assert safe_upload_filename("a\nb.png") == "ab.png"
    assert len(safe_upload_filename("x" * 400 + ".png") or "") == 255


@pytest.mark.asyncio
async def test_read_upload_limited_stops_at_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    limit = 1024 * 1024
    ok = UploadFile(file=io.BytesIO(b"a" * limit), filename="ok.png")
    assert len(await read_upload_limited(ok)) == limit

    too_big = UploadFile(file=io.BytesIO(b"a" * (limit + 10)), filename="big.png")
    with pytest.raises(ImageValidationError):
        await read_upload_limited(too_big)
