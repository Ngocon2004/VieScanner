from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, VieScannerError
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.cccd import CCCDData, ErrorResponse
from app.db.models.user import User
from app.models.record import CCCDRecordCreate, CCCDRecordRead, CCCDRecordUpdate
from app.db.repositories.cccd_record_repository import CCCDRecordRepository

router = APIRouter(prefix="/records")


@router.get("", response_model=list[CCCDRecordRead], responses={401: {"model": ErrorResponse}})
async def list_records(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CCCDRecordRead]:
    repo = CCCDRecordRepository(db)
    records = await repo.list_by_user(user_id=user.id, limit=limit, offset=offset)
    return [CCCDRecordRead.model_validate(_to_read_payload(item)) for item in records]


@router.post("", response_model=CCCDRecordRead, responses={401: {"model": ErrorResponse}})
async def create_record(
    payload: CCCDRecordCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CCCDRecordRead:
    repo = CCCDRecordRepository(db)
    cccd_data = CCCDData(
        id_number=payload.id_number,
        full_name=payload.full_name,
        dob=payload.dob,
        gender=payload.gender,
        nationality=payload.nationality,
        origin=payload.origin,
        residence=payload.residence,
        expiry_date=payload.expiry_date,
    )
    record = await repo.create_from_cccd(data=cccd_data, scan_id=payload.scan_id, user_id=user.id)
    await db.commit()
    return CCCDRecordRead.model_validate(_to_read_payload(record))


@router.patch("/{record_id}", response_model=CCCDRecordRead, responses={401: {"model": ErrorResponse}})
async def update_record(
    record_id: str,
    payload: CCCDRecordUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CCCDRecordRead:
    repo = CCCDRecordRepository(db)
    record = await repo.get_by_id(record_id)
    if record is None:
        raise VieScannerError("Record not found.", code="record_not_found")
    if record.user_id != user.id:
        raise AuthorizationError("You cannot update this record.", code="record_forbidden")

    updated = await repo.update_record(
        record=record,
        full_name=payload.full_name,
        dob=payload.dob,
        gender=payload.gender,
        nationality=payload.nationality,
        origin=payload.origin,
        residence=payload.residence,
        expiry_date=payload.expiry_date,
    )
    await db.commit()
    return CCCDRecordRead.model_validate(_to_read_payload(updated))


@router.delete("/{record_id}", responses={401: {"model": ErrorResponse}})
async def delete_record(
    record_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    repo = CCCDRecordRepository(db)
    record = await repo.get_by_id(record_id)
    if record is None:
        raise VieScannerError("Record not found.", code="record_not_found")
    if record.user_id != user.id:
        raise AuthorizationError("You cannot delete this record.", code="record_forbidden")

    await repo.delete_record(record)
    await db.commit()
    return {"status": "deleted"}


def _to_read_payload(record) -> dict:
    from app.db.repositories.cccd_record_repository import _format_ddmmyyyy

    return {
        "id": record.id,
        "scan_id": record.scan_id,
        "user_id": record.user_id,
        "id_number": record.id_number,
        "full_name": record.full_name,
        "dob": _format_ddmmyyyy(record.dob),
        "gender": record.gender,
        "nationality": record.nationality,
        "origin": record.origin,
        "residence": record.residence,
        "expiry_date": _format_ddmmyyyy(record.expiry_date),
        "exported_at": record.exported_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }

