"""Export endpoint: convert CCCDData to Excel and persist export metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ExcelGenerationError
from app.core.logging import logger
from app.db.session import get_db
from app.dependencies.auth import get_optional_user
from app.models.cccd import CCCDData, ErrorResponse
from app.db.models.user import User
from app.models.record import ExportRequest
from app.db.repositories.cccd_record_repository import CCCDRecordRepository
from app.db.repositories.correction_repository import CorrectionRepository
from app.db.repositories.scan_repository import ScanRepository
from app.services.excel_service import generate_excel
from app.utils.filename import build_content_disposition

router = APIRouter()


@router.post(
    "/export",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "Excel file",
        },
        500: {"model": ErrorResponse, "description": "Excel generation failed"},
    },
    summary="Export CCCD data to Excel",
)
async def export_to_excel(
    payload: ExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> Response:
    data, record_id, scan_id = _normalize_export_payload(payload)
    logger.info("export: id_number={} name={}", data.id_number, data.full_name)

    try:
        record_repo = CCCDRecordRepository(db)
        record = None

        if record_id:
            record = await record_repo.get_by_id(record_id)
            if record is not None and record.user_id and (user is None or record.user_id != user.id):
                raise AuthorizationError("You cannot export this record.", code="record_forbidden")

        if record is None:
            record = await record_repo.create_from_cccd(
                data=data,
                scan_id=scan_id,
                user_id=user.id if user else None,
            )
        else:
            await record_repo.update_record(
                record=record,
                full_name=data.full_name,
                dob=data.dob,
                gender=data.gender,
                nationality=data.nationality,
                origin=data.origin,
                residence=data.residence,
                expiry_date=data.expiry_date,
            )

        await record_repo.mark_exported(record)
        await _log_corrections_if_any(db=db, scan_id=scan_id or record.scan_id, final_data=data)
        await db.commit()
    except AuthorizationError:
        await db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("export metadata persistence skipped: {}", exc)

    try:
        excel_bytes = generate_excel(data)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("Excel generation failed")
        raise ExcelGenerationError(f"Cannot generate Excel file: {exc}") from exc

    filename = f"CCCD_{data.full_name}.xlsx" if data.full_name else "CCCD.xlsx"
    return Response(
        content=excel_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": build_content_disposition(filename)},
    )


def _normalize_export_payload(payload: ExportRequest) -> tuple[CCCDData, str | None, str | None]:
    if payload.data is not None:
        return payload.data, payload.record_id, payload.scan_id

    raw = {
        "id_number": payload.id_number,
        "full_name": payload.full_name,
        "dob": payload.dob,
        "gender": payload.gender,
        "nationality": payload.nationality,
        "origin": payload.origin,
        "residence": payload.residence,
        "expiry_date": payload.expiry_date,
    }
    try:
        data = CCCDData.model_validate(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    return data, payload.record_id, payload.scan_id


async def _log_corrections_if_any(
    *,
    db: AsyncSession,
    scan_id: str | None,
    final_data: CCCDData,
) -> None:
    if not scan_id:
        return

    scan_repo = ScanRepository(db)
    scan = await scan_repo.get_by_id(scan_id)
    if scan is None or not scan.raw_data:
        return

    original = scan.raw_data
    final = final_data.model_dump()
    confidences = scan.confidences or {}

    corrections: list[dict] = []
    for field_name, corrected_value in final.items():
        ocr_value = original.get(field_name)
        if str(ocr_value or "") == str(corrected_value or ""):
            continue
        corrections.append(
            {
                "field_name": field_name,
                "ocr_value": ocr_value,
                "corrected_value": corrected_value,
                "confidence_at_ocr": confidences.get(field_name),
            }
        )

    if corrections:
        repo = CorrectionRepository(db)
        await repo.bulk_insert(scan_id=scan_id, items=corrections)

