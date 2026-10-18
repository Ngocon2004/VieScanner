"""OCR endpoint: extract CCCD data from uploaded image."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ImageQualityError, ImageValidationError, OCRFailedError
from app.core.logging import logger
from app.db.models.scan import ScanStatus
from app.db.models.user import User
from app.db.repositories.scan_repository import ScanRepository
from app.db.session import SessionLocal, get_db
from app.dependencies.auth import get_optional_user
from app.models.cccd import (
    BatchExtractResponse,
    BatchItemResult,
    CCCDExtractResponse,
    ErrorResponse,
)
from app.services.extraction import (
    CRASH_MESSAGE,
    assess_quality,
    elapsed_ms,
    load_cached_response,
    process_upload,
    receive_upload,
    reject_message,
    summarize_hard_issues,
)
from app.services.ocr.version import engine_label
from app.services.ocr_engine import OCREngine, get_ocr_engine
from app.utils.image import safe_upload_filename

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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CCCD front image"),
    engine: OCREngine = Depends(get_ocr_engine),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> CCCDExtractResponse:
    upload = await receive_upload(file)
    logger.info(
        "extract: filename={} size={} mime={}",
        upload.filename,
        len(upload.contents),
        upload.mime_type,
    )

    started = perf_counter()
    request_id = getattr(request.state, "request_id", None)
    user_id = user.id if user else None

    def scan_fields(**overrides) -> dict:
        return {
            "user_id": user_id,
            "request_id": request_id,
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
        # Đường lỗi `raise` nên phải ghi đồng bộ: BackgroundTasks không chạy khi request lỗi.
        await _log_scan(db=db, **scan_fields(
            status=ScanStatus.FAILED,
            error_code="image_quality_low",
            error_message=summarize_hard_issues(quality),
        ))
        raise ImageQualityError(
            reject_message(quality),
            details=[issue.model_dump() for issue in quality.issues],
        )

    try:
        response = await load_cached_response(
            repo=ScanRepository(db), image_hash=upload.image_hash, user_id=user_id
        )
        label = engine_label(cached=True)
        if response is None:
            response = await engine.extract(upload.contents)
            label = engine_label()
        else:
            logger.info("extract cache hit: image_hash={}", upload.image_hash[:12])
    except OCRFailedError as exc:
        await _log_scan(db=db, **scan_fields(
            status=ScanStatus.FAILED, error_code=exc.code, error_message=exc.message,
        ))
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("OCR engine crashed")
        await _log_scan(db=db, **scan_fields(
            status=ScanStatus.FAILED, error_code="ocr_engine_crashed", error_message=str(exc),
        ))
        raise OCRFailedError(CRASH_MESSAGE, code="ocr_engine_crashed") from exc

    scan_id = str(uuid4())
    _schedule_scan(background_tasks, scan_id=scan_id, **scan_fields(
        ocr_engine=label,
        status=ScanStatus.SUCCESS,
        raw_data=response.data.model_dump(),
        confidences=response.confidences,
    ))
    response.scan_id = scan_id
    response.quality = quality
    return response


@router.post(
    "/extract-batch",
    response_model=BatchExtractResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid upload"},
    },
    summary="Phân loại + trích xuất nhiều ảnh CCCD cùng lúc (đồng bộ)",
    description="Giữ để tương thích ngược. Nhiều ảnh hoặc PDF nên dùng `POST /api/jobs`.",
)
async def extract_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="Danh sách ảnh CCCD mặt trước"),
    engine: OCREngine = Depends(get_ocr_engine),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> BatchExtractResponse:
    if not files:
        raise ImageValidationError("Chưa chọn ảnh nào để xử lý.")
    max_files = settings.quality_max_batch_files
    if len(files) > max_files:
        raise ImageValidationError(
            f"Chỉ xử lý tối đa {max_files} ảnh mỗi lần (bạn gửi {len(files)})."
        )

    request_id = getattr(request.state, "request_id", None)
    user_id = user.id if user else None
    repo = ScanRepository(db)
    seen: dict[str, CCCDExtractResponse] = {}

    results: list[BatchItemResult] = []
    for index, file in enumerate(files):
        try:
            upload = await receive_upload(file)
        except ImageValidationError as exc:
            results.append(BatchItemResult(
                index=index, filename=safe_upload_filename(file.filename), accepted=False,
                status="rejected", quality=None, error_code=exc.code, error_message=exc.message,
            ))
            continue

        outcome = await process_upload(
            index=index, upload=upload, engine=engine, repo=repo, seen=seen, user_id=user_id
        )
        scan_id = str(uuid4())
        _schedule_scan(background_tasks, scan_id=scan_id, request_id=request_id, **outcome.scan)
        if outcome.result.status == "extracted":
            outcome.result.scan_id = scan_id
        results.append(outcome.result)

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


async def _log_scan(*, db: AsyncSession, **fields) -> str | None:
    try:
        scan = await ScanRepository(db).create_scan(**fields)
        await db.commit()
        return scan.id
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("scan logging skipped: {}", exc)
        return None


def _schedule_scan(background_tasks: BackgroundTasks, *, scan_id: str, **fields) -> None:
    """M4: lên lịch ghi 1 scan SAU khi response đã gửi (FastAPI BackgroundTasks).

    Chỉ dùng khi endpoint return bình thường; đường lỗi `raise` phải dùng `_log_scan`
    đồng bộ vì background task không chạy khi request raise. `scan_id` được
    pre-generate để trả ngay trong response."""
    background_tasks.add_task(_persist_scan_bg, id=scan_id, **fields)


async def _persist_scan_bg(**fields) -> None:
    """Ghi scan ở background bằng session DB riêng (session của request đã đóng
    sau khi response gửi xong). Best-effort: lỗi chỉ log cảnh báo."""
    async with SessionLocal() as session:
        try:
            await ScanRepository(session).create_scan(**fields)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            logger.warning("background scan logging skipped: {}", exc)
