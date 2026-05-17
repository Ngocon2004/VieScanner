"""OCR endpoint: extract CCCD data from uploaded image."""

from __future__ import annotations

import hashlib
from time import perf_counter

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import OCRFailedError
from app.core.logging import logger
from app.db.session import get_db
from app.dependencies.auth import get_optional_user
from app.models.cccd import CCCDExtractResponse, ErrorResponse
from app.db.models.scan import ScanStatus
from app.db.models.user import User
from app.db.repositories.scan_repository import ScanRepository
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

    try:
        response = await engine.extract(contents)
        elapsed_ms = int((perf_counter() - started) * 1000)
        scan_id = await _log_scan(
            db=db,
            user_id=user.id if user else None,
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
        return response
    except OCRFailedError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        await _log_scan(
            db=db,
            user_id=user.id if user else None,
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
            user_id=user.id if user else None,
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

