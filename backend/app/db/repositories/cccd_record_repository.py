from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cccd import CCCDData
from app.db.models.cccd_record import CCCDRecord


def _parse_ddmmyyyy(value: str | None) -> datetime.date | None:
    if value is None or value == "":
        return None
    return datetime.strptime(value, "%d/%m/%Y").date()


def _format_ddmmyyyy(value: datetime.date | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%d/%m/%Y")


class CCCDRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_from_cccd(
        self,
        *,
        data: CCCDData,
        scan_id: str | None,
        user_id: str | None,
    ) -> CCCDRecord:
        record = CCCDRecord(
            scan_id=scan_id,
            user_id=user_id,
            id_number=data.id_number,
            full_name=data.full_name,
            dob=_parse_ddmmyyyy(data.dob),
            gender=data.gender,
            nationality=data.nationality,
            origin=data.origin,
            residence=data.residence,
            expiry_date=_parse_ddmmyyyy(data.expiry_date),
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_by_id(self, record_id: str) -> CCCDRecord | None:
        stmt = select(CCCDRecord).where(CCCDRecord.id == record_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_scan(self, *, scan_id: str, user_id: str | None) -> CCCDRecord | None:
        stmt = (
            select(CCCDRecord)
            .where(CCCDRecord.scan_id == scan_id, CCCDRecord.user_id == user_id)
            .order_by(desc(CCCDRecord.created_at))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_user(
        self,
        *,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CCCDRecord]:
        stmt = (
            select(CCCDRecord)
            .where(CCCDRecord.user_id == user_id)
            .order_by(desc(CCCDRecord.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_record(
        self,
        *,
        record: CCCDRecord,
        id_number: str | None = None,
        full_name: str | None = None,
        dob: str | None = None,
        gender: str | None = None,
        nationality: str | None = None,
        origin: str | None = None,
        residence: str | None = None,
        expiry_date: str | None = None,
    ) -> CCCDRecord:
        if id_number is not None:
            record.id_number = id_number
        if full_name is not None:
            record.full_name = full_name
        if dob is not None:
            record.dob = _parse_ddmmyyyy(dob)
        if gender is not None:
            record.gender = gender
        if nationality is not None:
            record.nationality = nationality
        if origin is not None:
            record.origin = origin
        if residence is not None:
            record.residence = residence
        if expiry_date is not None:
            record.expiry_date = _parse_ddmmyyyy(expiry_date)

        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def overwrite_from_cccd(self, *, record: CCCDRecord, data: CCCDData) -> CCCDRecord:
        await self.update_record(record=record, **data.model_dump())
        record.expiry_date = _parse_ddmmyyyy(data.expiry_date)
        await self.session.flush()
        return record

    async def delete_record(self, record: CCCDRecord) -> None:
        await self.session.delete(record)

    async def mark_exported(self, record: CCCDRecord) -> CCCDRecord:
        record.exported_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(record)
        return record


__all__ = [
    "CCCDRecordRepository",
    "_parse_ddmmyyyy",
    "_format_ddmmyyyy",
]

