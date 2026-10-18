"""Export endpoint: convert CCCDData to Excel and persist export metadata."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ExcelGenerationError
from app.core.logging import logger
from app.db.session import get_db
from app.dependencies.auth import get_optional_user
from app.models.cccd import CCCDData, ErrorResponse
from app.db.models.scan import Scan
from app.db.models.user import User
from app.models.record import ExportListRequest, ExportRequest
from app.db.repositories.cccd_record_repository import CCCDRecordRepository
from app.db.repositories.correction_repository import CorrectionRepository
from app.db.repositories.scan_repository import ScanRepository
from app.services.excel_service import generate_excel, generate_excel_list
from app.services.scan_access import attachable_scan
from app.utils.filename import build_content_disposition
from app.utils.privacy import mask_id_number

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
    user_id = user.id if user else None
    logger.info("export: id_number={}", mask_id_number(data.id_number))

    try:
        scan = await attachable_scan(db, scan_id, user_id)
        record_repo = CCCDRecordRepository(db)
        record = None

        if record_id:
            record = await record_repo.get_by_id(record_id)
            if record is not None and record.user_id and record.user_id != user_id:
                raise AuthorizationError("Bạn không có quyền với bản ghi này.", code="record_forbidden")
        # Xuất lại cùng một ảnh (sửa rồi bấm xuất lần nữa) phải cập nhật hồ sơ cũ, không tạo bản trùng.
        if record is None and scan is not None:
            record = await record_repo.get_latest_by_scan(scan_id=scan.id, user_id=user_id)

        if record is None:
            record = await record_repo.create_from_cccd(
                data=data,
                scan_id=scan.id if scan else None,
                user_id=user_id,
            )
        else:
            await record_repo.overwrite_from_cccd(record=record, data=data)

        await record_repo.mark_exported(record)
        if scan is None and record.scan_id:
            scan = await ScanRepository(db).get_by_id(record.scan_id)
        await _log_corrections_if_any(db=db, scan=scan, final=data.model_dump())
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
        logger.exception("Excel generation failed")
        raise ExcelGenerationError("Không tạo được file Excel.") from exc

    filename = f"CCCD_{data.full_name}.xlsx" if data.full_name else "CCCD.xlsx"
    return Response(
        content=excel_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": build_content_disposition(filename)},
    )


@router.post(
    "/export-list",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "Excel file, one row per person",
        },
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse, "description": "Excel generation failed"},
    },
    summary="Export a reviewed list of CCCD rows to one Excel file",
)
async def export_list_to_excel(
    payload: ExportListRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> Response:
    user_id = user.id if user else None
    logger.info("export list: rows={}", len(payload.rows))

    try:
        for row in payload.rows:
            final = row.model_dump(exclude={"scan_ids"})
            for scan_id in dict.fromkeys(row.scan_ids):
                try:
                    scan = await attachable_scan(db, scan_id, user_id)
                except AuthorizationError:
                    # Scan của tài khoản khác (vd. quét khi đăng nhập rồi đăng xuất mới xuất): không ghi
                    # corrections vào scan đó, nhưng vẫn xuất file vì dữ liệu dòng do chính người dùng gửi.
                    continue
                # Dòng ghép từ mặt trước + mặt sau: mỗi scan chỉ tính bản sửa cho trường nó đã đọc ra.
                await _log_corrections_if_any(db=db, scan=scan, final=final, only_read=True)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("export list corrections skipped: {}", exc)

    try:
        excel_bytes = generate_excel_list(payload.rows)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Excel list generation failed")
        raise ExcelGenerationError("Không tạo được file Excel.") from exc

    filename = f"DanhSach_CCCD_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
    scan: Scan | None,
    final: dict,
    only_read: bool = False,
) -> None:
    if scan is None:
        return
    # Đánh dấu đã xuất: trang quản trị tính tỉ lệ người dùng phải sửa trên các lượt quét này.
    scan.exported_at = datetime.now(timezone.utc)
    if not scan.raw_data:
        return

    original = scan.raw_data
    confidences = scan.confidences or {}

    corrections: list[dict] = []
    for field_name, corrected_value in final.items():
        if only_read and not confidences.get(field_name):
            continue
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

    await CorrectionRepository(db).replace_for_scan(scan_id=scan.id, items=corrections)

