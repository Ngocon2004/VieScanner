"""Xử lý 1 ảnh CCCD: kiểm chất lượng -> cache -> OCR.

Dùng chung cho `/extract-batch` và Job worker để hai luồng cho kết quả giống hệt nhau.
Không biết gì về HTTP hay cách ghi scan: trả về kết quả + dữ liệu scan để caller tự lưu.
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import nullcontext
from dataclasses import dataclass
from time import perf_counter

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import OCRFailedError
from app.core.logging import logger
from app.db.models.scan import ScanStatus
from app.db.repositories.scan_repository import ScanRepository
from app.models.cccd import BatchItemResult, CCCDData, CCCDExtractResponse
from app.models.quality import QualityReport
from app.services.image_quality import assess_image_quality
from app.services.ocr.review import review_issues
from app.services.ocr.version import engine_label
from app.services.ocr_engine import OCREngine, get_ocr_semaphore
from app.utils.image import read_upload_limited, safe_upload_filename, validate_image_bytes

CRASH_MESSAGE = "Lỗi không mong muốn khi trích xuất ảnh này."


@dataclass(frozen=True)
class Upload:
    filename: str | None
    mime_type: str
    contents: bytes
    image_hash: str


@dataclass
class Outcome:
    result: BatchItemResult
    scan: dict


def make_upload(filename: str | None, mime_type: str, contents: bytes) -> Upload:
    return Upload(
        filename=filename,
        mime_type=mime_type,
        contents=contents,
        image_hash=hashlib.sha256(contents).hexdigest(),
    )


async def receive_upload(file: UploadFile) -> Upload:
    contents = await read_upload_limited(file)
    mime_type = validate_image_bytes(file.content_type, contents)
    return make_upload(safe_upload_filename(file.filename), mime_type, contents)


def elapsed_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


async def assess_quality(contents: bytes) -> QualityReport:
    """Chạy cổng kiểm tra chất lượng trong thread (CPU/GPU-bound). Degrade an toàn."""
    if not settings.quality_check_enabled:
        return QualityReport(accepted=True, score=1.0)
    run_card = (
        settings.quality_card_check_enabled
        and settings.ocr_engine.lower() == "real"
    )
    # Kiểm tra thẻ dùng YOLO (không thread-safe) nên phải chung giới hạn đồng thời với OCR.
    guard = get_ocr_semaphore() if run_card else nullcontext()
    try:
        async with guard:
            return await asyncio.to_thread(
                assess_image_quality, contents, run_card_check=run_card
            )
    except Exception as exc:  # noqa: BLE001 – không để quality check làm hỏng request.
        logger.warning("quality assessment skipped: {}", exc)
        return QualityReport(accepted=True, score=1.0)


def summarize_hard_issues(quality: QualityReport) -> str:
    msgs = [i.message for i in quality.issues if i.severity == "hard"]
    return " ".join(msgs)[:480] if msgs else "Ảnh không đạt tiêu chuẩn."


def reject_message(quality: QualityReport) -> str:
    return f"Ảnh không đạt tiêu chuẩn để trích xuất. {summarize_hard_issues(quality)}".strip()


async def load_cached_response(
    *,
    repo: ScanRepository,
    image_hash: str,
    user_id: str | None,
) -> CCCDExtractResponse | None:
    if not settings.ocr_result_cache_enabled:
        return None
    try:
        cached_scan = await repo.get_latest_success_by_image_hash(
            image_hash=image_hash,
            user_id=user_id,
            ocr_engine=engine_label(),
            ttl_seconds=settings.ocr_result_cache_ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("scan cache lookup skipped: {}", exc)
        return None
    if cached_scan is None or not isinstance(cached_scan.raw_data, dict):
        return None
    try:
        data = CCCDData.model_validate(cached_scan.raw_data)
    except Exception:  # noqa: BLE001
        return None
    confidences = cached_scan.confidences if isinstance(cached_scan.confidences, dict) else {}
    return CCCDExtractResponse(data=data, confidences=confidences)


async def process_upload(
    *,
    index: int,
    upload: Upload,
    engine: OCREngine,
    repo: ScanRepository,
    seen: dict[str, CCCDExtractResponse],
    user_id: str | None,
) -> Outcome:
    """Không bao giờ raise: mọi lỗi được gói vào `BatchItemResult`.

    `seen` gom kết quả theo hash ảnh trong cùng một lần xử lý: ảnh trùng chỉ OCR một lần
    (scan của lần đầu có thể chưa kịp ghi DB nên cache DB không bắt được).
    """
    started = perf_counter()

    def scan(**overrides) -> dict:
        return {
            "user_id": user_id,
            "filename": upload.filename,
            "mime_type": upload.mime_type,
            "size_bytes": len(upload.contents),
            "image_hash": upload.image_hash,
            "ocr_engine": engine_label(),
            "raw_data": None,
            "confidences": None,
            "error_code": None,
            "error_message": None,
            "duration_ms": elapsed_ms(started),
            **overrides,
        }

    quality = await assess_quality(upload.contents)
    if not quality.accepted:
        return Outcome(
            BatchItemResult(
                index=index, filename=upload.filename, accepted=False, status="rejected",
                quality=quality, error_code="image_quality_low",
                error_message=reject_message(quality),
            ),
            scan(
                status=ScanStatus.FAILED,
                error_code="image_quality_low",
                error_message=summarize_hard_issues(quality),
            ),
        )

    label = engine_label(cached=True)
    try:
        response = seen.get(upload.image_hash) or await load_cached_response(
            repo=repo, image_hash=upload.image_hash, user_id=user_id
        )
        if response is None:
            response = await engine.extract(upload.contents)
            label = engine_label()
    except OCRFailedError as exc:
        return Outcome(
            BatchItemResult(
                index=index, filename=upload.filename, accepted=True, status="ocr_failed",
                quality=quality, error_code=exc.code, error_message=exc.message,
            ),
            scan(status=ScanStatus.FAILED, error_code=exc.code, error_message=exc.message),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("OCR crashed | index={}", index)
        return Outcome(
            BatchItemResult(
                index=index, filename=upload.filename, accepted=True, status="ocr_failed",
                quality=quality, error_code="ocr_engine_crashed", error_message=CRASH_MESSAGE,
            ),
            scan(status=ScanStatus.FAILED, error_code="ocr_engine_crashed", error_message=str(exc)),
        )

    seen[upload.image_hash] = response
    # Cache DB chỉ lưu dữ liệu + confidence nên cảnh báo "cần xem lại" được tính lại từ confidence.
    review = response.quality.issues if response.quality is not None else review_issues(response.confidences)
    if review:
        quality = quality.model_copy(update={"issues": [*quality.issues, *review]})
    return Outcome(
        BatchItemResult(
            index=index, filename=upload.filename, accepted=True, status="extracted",
            quality=quality, data=response.data, confidences=response.confidences,
        ),
        scan(
            ocr_engine=label,
            status=ScanStatus.SUCCESS,
            raw_data=response.data.model_dump(),
            confidences=response.confidences,
        ),
    )


__all__ = [
    "CRASH_MESSAGE",
    "Outcome",
    "Upload",
    "assess_quality",
    "elapsed_ms",
    "load_cached_response",
    "make_upload",
    "process_upload",
    "receive_upload",
    "reject_message",
    "summarize_hard_issues",
]
