"""Tiếp nhận file cho Job: chuẩn hóa mọi định dạng thành danh sách ảnh để OCR.

- JPG/PNG/WebP: giữ nguyên (validate magic bytes như `/extract`).
- HEIC/HEIF (iPhone): giải mã bằng pillow-heif, xoay theo EXIF, xuất JPEG.
- PDF: render từng trang bằng pypdfium2 (giấy phép Apache/BSD) thành JPEG.
- Ảnh/trang chụp nhiều thẻ: tách thành từng ảnh một thẻ (`card_split`).

Chia 2 bước để request tạo job trả về ngay: `plan_upload` (trong request) chỉ nhận diện định dạng và đếm
trang PDF; `prepare_item` (trong worker) mới render trang, đổi HEIC, tách thẻ. Làm hết trong request từng
khiến PDF 100 trang chờ 13s trước khi có job id.

File lỗi không làm hỏng cả lô: trả về item có `error_*` để báo riêng cho người dùng.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, replace
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.core.exceptions import ImageValidationError
from app.core.logging import logger
from app.services.card_split import split_cards
from app.utils.image import detect_image_mime, validate_image_bytes

_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
_JPEG_QUALITY = 90
_PDF_MAX_RENDER_SIDE_PX = 4000
_CHUNK_BYTES = 1024 * 1024
_UNREADABLE_MESSAGE = "Không đọc được file (hỏng hoặc được bảo vệ bằng mật khẩu)."

# File upload đã ghi ra đĩa (job) hoặc nằm trong bộ nhớ (`expand_file`).
Source = bytes | Path


@dataclass
class IntakeItem:
    upload_index: int
    filename: str | None
    mime_type: str | None = None
    contents: bytes | None = None
    container_filename: str | None = None
    page_number: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class IntakeLimitError(ImageValidationError):
    code = "import_too_large"


def sniff_kind(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
        return "heic"
    if detect_image_mime(data):
        return "image"
    return None


def save_upload(stream: BinaryIO, path: Path) -> None:
    """Chép file upload ra đĩa theo khối 1MB, không nạp cả file vào RAM. Chạy trong thread (I/O đồng bộ)."""
    limit = max(settings.max_upload_size_bytes, settings.import_max_file_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with path.open("wb") as out:
        while chunk := stream.read(_CHUNK_BYTES):
            size += len(chunk)
            if size > limit:
                break
            out.write(chunk)
    if size > limit or size == 0:
        path.unlink(missing_ok=True)
        raise ImageValidationError(
            f"Kích thước file vượt quá {limit // (1024 * 1024)}MB." if size else "File rỗng."
        )


def _read(source: Source, size: int = -1) -> bytes:
    if isinstance(source, bytes):
        return source if size < 0 else source[:size]
    with source.open("rb") as f:
        return f.read(size)


def _size(source: Source) -> int:
    return len(source) if isinstance(source, bytes) else source.stat().st_size


def _open_pdf(source: Source):  # noqa: ANN202 – pypdfium2.PdfDocument
    import pypdfium2 as pdfium

    return pdfium.PdfDocument(source if isinstance(source, bytes) else str(source))


def _encode_jpeg(image) -> bytes:  # noqa: ANN001 – PIL.Image
    max_side = max(0, int(settings.ocr_max_image_side_px))
    if max_side and max(image.size) > max_side:
        image.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return buf.getvalue()


def _heic_to_jpeg(data: bytes) -> bytes:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    with Image.open(io.BytesIO(data)) as img:
        return _encode_jpeg(ImageOps.exif_transpose(img))


def _pdf_page_count(source: Source) -> int:
    pdf = _open_pdf(source)
    try:
        pages = len(pdf)
    finally:
        pdf.close()
    if pages > settings.import_pdf_max_pages:
        raise ImageValidationError(
            f"PDF có {pages} trang, vượt giới hạn {settings.import_pdf_max_pages} trang.",
            code="pdf_too_many_pages",
        )
    if pages == 0:
        raise ImageValidationError("PDF không có trang nào.")
    return pages


def _render_pdf_page(source: Source, page_number: int) -> bytes:
    pdf = _open_pdf(source)
    try:
        page = pdf[page_number - 1]
        try:
            # Giới hạn kích thước bitmap theo cạnh dài: trang khổ lớn ở DPI cao có thể
            # cần hàng GB RAM, trong khi OCR chỉ dùng ảnh đã thu về `max_side`.
            max_side = int(settings.ocr_max_image_side_px) or _PDF_MAX_RENDER_SIDE_PX
            scale = min(settings.import_pdf_dpi / 72, max_side / max(1.0, *page.get_size()))
            return _encode_jpeg(page.render(scale=scale).to_pil())
        finally:
            page.close()
    finally:
        pdf.close()


def _error_item(item: IntakeItem, exc: Exception) -> IntakeItem:
    if isinstance(exc, ImageValidationError):
        return replace(item, error_code=exc.code, error_message=exc.message)
    # File hỏng/mã hóa: báo lỗi riêng file đó.
    logger.warning("intake failed | file={} | {}", item.filename, exc)
    return replace(item, error_code="file_unreadable", error_message=_UNREADABLE_MESSAGE)


def plan_upload(upload_index: int, filename: str | None, source: Source) -> list[IntakeItem]:
    """Các ảnh/trang cần OCR của 1 file, chưa giải mã ảnh: chỉ đọc vài byte đầu và mục lục PDF."""
    item = IntakeItem(upload_index, filename)
    try:
        head = _read(source, 16)
        kind = sniff_kind(head)
        if kind == "image":
            if _size(source) > settings.max_upload_size_bytes:
                raise ImageValidationError(f"Kích thước file vượt quá {settings.max_upload_size_mb}MB.")
            return [replace(item, mime_type=validate_image_bytes(None, head))]
        if kind == "heic":
            if _size(source) > settings.max_upload_size_bytes:
                raise ImageValidationError(f"Kích thước file vượt quá {settings.max_upload_size_mb}MB.")
            return [replace(item, mime_type="image/jpeg")]
        if kind == "pdf":
            return [
                IntakeItem(
                    upload_index,
                    f"{filename or 'document.pdf'} - trang {n}",
                    "image/jpeg",
                    container_filename=filename,
                    page_number=n,
                )
                for n in range(1, _pdf_page_count(source) + 1)
            ]
        raise ImageValidationError(
            "Định dạng không được hỗ trợ. Chỉ nhận JPG, PNG, WebP, HEIC hoặc PDF.",
            code="unsupported_file",
        )
    except Exception as exc:  # noqa: BLE001
        return [_error_item(item, exc)]


def prepare_item(item: IntakeItem, source: Source) -> list[IntakeItem]:
    """Ảnh cần OCR của 1 item từ `plan_upload` (render trang PDF, đổi HEIC, tách ảnh nhiều thẻ). CPU-bound."""
    try:
        if item.page_number is not None:
            prepared = replace(item, mime_type="image/jpeg", contents=_render_pdf_page(source, item.page_number))
        else:
            data = _read(source)
            if sniff_kind(data) == "heic":
                prepared = replace(item, mime_type="image/jpeg", contents=_heic_to_jpeg(data))
            else:
                prepared = replace(item, mime_type=validate_image_bytes(None, data), contents=data)
    except Exception as exc:  # noqa: BLE001
        return [_error_item(item, exc)]
    return _split_item(prepared) if settings.import_split_multi_cards else [prepared]


def expand_file(upload_index: int, filename: str | None, data: bytes) -> list[IntakeItem]:
    """Cả 2 bước cho 1 file trong bộ nhớ. CPU-bound: caller nên chạy trong thread."""
    return [
        prepared
        for planned in plan_upload(upload_index, filename, data)
        for prepared in ([planned] if planned.error_code else prepare_item(planned, data))
    ]


def _split_item(item: IntakeItem) -> list[IntakeItem]:
    try:
        crops = split_cards(item.contents)
    except Exception as exc:  # noqa: BLE001 – tách lỗi thì vẫn OCR cả ảnh như trước.
        logger.warning("split cards failed | file={} | {}", item.filename, exc)
        return [item]
    return [
        IntakeItem(
            item.upload_index,
            f"{item.filename or 'ảnh'} - thẻ {n}",
            "image/jpeg",
            crop,
            container_filename=item.container_filename or item.filename,
            page_number=item.page_number,
        )
        for n, crop in enumerate(crops, start=1)
    ] or [item]


__all__ = [
    "IntakeItem",
    "IntakeLimitError",
    "expand_file",
    "plan_upload",
    "prepare_item",
    "save_upload",
    "sniff_kind",
]
