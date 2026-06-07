"""OCR endpoint: extract CCCD data from uploaded image."""

from __future__ import annotations

import asyncio
import hashlib
from time import perf_counter

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ImageQualityError, ImageValidationError, OCRFailedError
from app.core.logging import logger
from app.db.session import get_db
from app.dependencies.auth import get_optional_user
from app.models.cccd import (
    BatchExtractResponse,
    BatchItemResult,
    CCCDData,
    CCCDExtractResponse,
    ErrorResponse,
)
from app.models.quality import QualityReport
from app.db.models.scan import ScanStatus
from app.db.models.user import User
from app.db.repositories.scan_repository import ScanRepository
from app.services.image_quality import assess_image_quality
from app.services.ocr_engine import OCREngine, get_ocr_engine
from app.utils.image import validate_image_bytes

router = APIRouter()


@router.post(
    "/extract",
    response_model=CCCDExtractResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image"},
        422: {"model": ErrorResponse, "description": "OCR failed"},
    },
    summary="Extract CCCD fields from an image",
)
async def extract_cccd(
    request: Request,
    file: UploadFile = File(..., description="CCCD front image"),
    engine: OCREngine = Depends(get_ocr_engine),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> CCCDExtractResponse:
    contents = await file.read()
    validate_image_bytes(file.content_type, contents)

    logger.info(
        "extract: filename={} size={} mime={}",
        file.filename,
        len(contents),
        file.content_type,
    )

    started = perf_counter()
    image_hash = hashlib.sha256(contents).hexdigest()
    request_id = getattr(request.state, "request_id", None)
    user_id = user.id if user else None
    repo = ScanRepository(db)

    quality = await _assess_quality(contents)
    if not quality.accepted:
        elapsed_ms = int((perf_counter() - started) * 1000)
        await _log_scan(
            db=db,
            user_id=user_id,
            request_id=request_id,
            filename=file.filename,
            mime_type=file.content_type,
            size_bytes=len(contents),
            image_hash=image_hash,
            ocr_engine=settings.ocr_engine,
            status=ScanStatus.FAILED,
            raw_data=None,
            confidences=None,
            error_code="image_quality_low",
            error_message=_summarize_hard_issues(quality),
            duration_ms=elapsed_ms,
        )
        raise ImageQualityError(
            _reject_message(quality),
            details=[issue.model_dump() for issue in quality.issues],
        )

    try:
        cached_response = await _load_cached_response(
            repo=repo,
            image_hash=image_hash,
            user_id=user_id,
        )
        if cached_response is not None:
            elapsed_ms = int((perf_counter() - started) * 1000)
            scan_id = await _log_scan(
                db=db,
                user_id=user_id,
                request_id=request_id,
                filename=file.filename,
                mime_type=file.content_type,
                size_bytes=len(contents),
                image_hash=image_hash,
                ocr_engine=f"{settings.ocr_engine}:cache",
                status=ScanStatus.SUCCESS,
                raw_data=cached_response.data.model_dump(),
                confidences=cached_response.confidences,
                error_code=None,
                error_message=None,
                duration_ms=elapsed_ms,
            )
            cached_response.scan_id = scan_id
            cached_response.quality = quality
            logger.info("extract cache hit: image_hash={} scan_id={}", image_hash[:12], scan_id)
            return cached_response

        response = await engine.extract(contents)
        elapsed_ms = int((perf_counter() - started) * 1000)
        scan_id = await _log_scan(
            db=db,
            user_id=user_id,
            request_id=request_id,
            filename=file.filename,
            mime_type=file.content_type,
            size_bytes=len(contents),
            image_hash=image_hash,
            ocr_engine=settings.ocr_engine,
            status=ScanStatus.SUCCESS,
            raw_data=response.data.model_dump(),
            confidences=response.confidences,
            error_code=None,
            error_message=None,
            duration_ms=elapsed_ms,
        )
        response.scan_id = scan_id
        response.quality = quality
        return response
    except OCRFailedError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        await _log_scan(
            db=db,
            user_id=user_id,
            request_id=request_id,
            filename=file.filename,
            mime_type=file.content_type,
            size_bytes=len(contents),
            image_hash=image_hash,
            ocr_engine=settings.ocr_engine,
            status=ScanStatus.FAILED,
            raw_data=None,
            confidences=None,
            error_code=exc.code,
            error_message=exc.message,
            duration_ms=elapsed_ms,
        )
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("OCR engine crashed")
        elapsed_ms = int((perf_counter() - started) * 1000)
        await _log_scan(
            db=db,
            user_id=user_id,
            request_id=request_id,
            filename=file.filename,
            mime_type=file.content_type,
            size_bytes=len(contents),
            image_hash=image_hash,
            ocr_engine=settings.ocr_engine,
            status=ScanStatus.FAILED,
            raw_data=None,
            confidences=None,
            error_code="ocr_engine_crashed",
            error_message=str(exc),
            duration_ms=elapsed_ms,
        )
        raise OCRFailedError(f"Cannot extract information: {exc}") from exc


@router.post(
    "/extract-batch",
    response_model=BatchExtractResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid upload"},
    },
    summary="Phân loại + trích xuất nhiều ảnh CCCD cùng lúc",
)
async def extract_batch(
    request: Request,
    files: list[UploadFile] = File(..., description="Danh sách ảnh CCCD mặt trước"),
    engine: OCREngine = Depends(get_ocr_engine),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> BatchExtractResponse:
    """Mỗi ảnh được kiểm tra chất lượng trước; ảnh đạt thì OCR, ảnh không đạt thì
    trả lý do cụ thể. Một ảnh lỗi không làm hỏng cả batch."""
    if not files:
        raise ImageValidationError("Chưa chọn ảnh nào để xử lý.")
    max_files = settings.quality_max_batch_files
    if len(files) > max_files:
        raise ImageValidationError(
            f"Chỉ xử lý tối đa {max_files} ảnh mỗi lần (bạn gửi {len(files)})."
        )

    request_id = getattr(request.state, "request_id", None)
    user_id = user.id if user else None

    results: list[BatchItemResult] = []
    # Xử lý tuần tự để tránh nhiều thread cùng dùng 1 model (không thread-safe).
    for index, file in enumerate(files):
        results.append(
            await _process_batch_item(
                index=index,
                file=file,
                engine=engine,
                db=db,
                request_id=request_id,
                user_id=user_id,
            )
        )

    accepted_count = sum(1 for r in results if r.accepted)
    rejected_count = len(results) - accepted_count
    logger.info(
        "extract-batch done | total={} accepted={} rejected={}",
        len(results), accepted_count, rejected_count,
    )
    return BatchExtractResponse(
        total=len(results),
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        results=results,
    )


async def _process_batch_item(
    *,
    index: int,
    file: UploadFile,
    engine: OCREngine,
    db: AsyncSession,
    request_id: str | None,
    user_id: str | None,
) -> BatchItemResult:
    """Xử lý 1 ảnh trong batch – không bao giờ raise (gói lỗi vào kết quả)."""
    filename = file.filename
    started = perf_counter()
    contents = await file.read()

    # 1) Định dạng/kích thước/magic bytes.
    try:
        validate_image_bytes(file.content_type, contents)
    except ImageValidationError as exc:
        return BatchItemResult(
            index=index, filename=filename, accepted=False, status="rejected",
            quality=None, error_code=exc.code, error_message=exc.message,
        )

    image_hash = hashlib.sha256(contents).hexdigest()

    # 2) Chất lượng ảnh.
    quality = await _assess_quality(contents)
    if not quality.accepted:
        elapsed_ms = int((perf_counter() - started) * 1000)
        await _log_scan(
            db=db, user_id=user_id, request_id=request_id,
            filename=filename, mime_type=file.content_type,
            size_bytes=len(contents), image_hash=image_hash,
            ocr_engine=settings.ocr_engine, status=ScanStatus.FAILED,
            raw_data=None, confidences=None,
            error_code="image_quality_low",
            error_message=_summarize_hard_issues(quality),
            duration_ms=elapsed_ms,
        )
        return BatchItemResult(
            index=index, filename=filename, accepted=False, status="rejected",
            quality=quality, error_code="image_quality_low",
            error_message=_reject_message(quality),
        )

    # 3) OCR (ảnh đã đạt cổng chất lượng).
    try:
        response = await engine.extract(contents)
    except OCRFailedError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        await _log_scan(
            db=db, user_id=user_id, request_id=request_id,
            filename=filename, mime_type=file.content_type,
            size_bytes=len(contents), image_hash=image_hash,
            ocr_engine=settings.ocr_engine, status=ScanStatus.FAILED,
            raw_data=None, confidences=None,
            error_code=exc.code, error_message=exc.message,
            duration_ms=elapsed_ms,
        )
        return BatchItemResult(
            index=index, filename=filename, accepted=True, status="ocr_failed",
            quality=quality, error_code=exc.code, error_message=exc.message,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("batch item OCR crashed | index={}", index)
        elapsed_ms = int((perf_counter() - started) * 1000)
        await _log_scan(
            db=db, user_id=user_id, request_id=request_id,
            filename=filename, mime_type=file.content_type,
            size_bytes=len(contents), image_hash=image_hash,
            ocr_engine=settings.ocr_engine, status=ScanStatus.FAILED,
            raw_data=None, confidences=None,
            error_code="ocr_engine_crashed", error_message=str(exc),
            duration_ms=elapsed_ms,
        )
        return BatchItemResult(
            index=index, filename=filename, accepted=True, status="ocr_failed",
            quality=quality, error_code="ocr_engine_crashed",
            error_message="Lỗi không mong muốn khi trích xuất ảnh này.",
        )

    elapsed_ms = int((perf_counter() - started) * 1000)
    scan_id = await _log_scan(
        db=db, user_id=user_id, request_id=request_id,
        filename=filename, mime_type=file.content_type,
        size_bytes=len(contents), image_hash=image_hash,
        ocr_engine=settings.ocr_engine, status=ScanStatus.SUCCESS,
        raw_data=response.data.model_dump(), confidences=response.confidences,
        error_code=None, error_message=None, duration_ms=elapsed_ms,
    )
    return BatchItemResult(
        index=index, filename=filename, accepted=True, status="extracted",
        quality=quality, data=response.data, confidences=response.confidences,
        scan_id=scan_id,
    )


async def _assess_quality(contents: bytes) -> QualityReport:
    """Chạy cổng kiểm tra chất lượng trong thread (CPU/GPU-bound). Degrade an toàn."""
    if not settings.quality_check_enabled:
        return QualityReport(accepted=True, score=1.0)
    run_card = (
        settings.quality_card_check_enabled
        and settings.ocr_engine.lower() == "real"
    )
    try:
        return await asyncio.to_thread(
            assess_image_quality, contents, run_card_check=run_card
        )
    except Exception as exc:  # noqa: BLE001 – không để quality check làm hỏng request.
        logger.warning("quality assessment skipped: {}", exc)
        return QualityReport(accepted=True, score=1.0)


def _summarize_hard_issues(quality: QualityReport) -> str:
    msgs = [i.message for i in quality.issues if i.severity == "hard"]
    return " ".join(msgs)[:480] if msgs else "Ảnh không đạt tiêu chuẩn."


def _reject_message(quality: QualityReport) -> str:
    summary = _summarize_hard_issues(quality)
    return f"Ảnh không đạt tiêu chuẩn để trích xuất. {summary}".strip()


async def _load_cached_response(
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


async def _log_scan(
    *,
    db: AsyncSession,
    user_id: str | None,
    request_id: str | None,
    filename: str | None,
    mime_type: str | None,
    size_bytes: int | None,
    image_hash: str | None,
    ocr_engine: str,
    status: ScanStatus,
    raw_data: dict | None,
    confidences: dict | None,
    error_code: str | None,
    error_message: str | None,
    duration_ms: int | None,
) -> str | None:
    repo = ScanRepository(db)
    try:
        scan = await repo.create_scan(
            user_id=user_id,
            request_id=request_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            image_hash=image_hash,
            ocr_engine=ocr_engine,
            status=status,
            raw_data=raw_data,
            confidences=confidences,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        await db.commit()
        return scan.id
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("scan logging skipped: {}", exc)
        return None

