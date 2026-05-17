from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.scan import Scan, ScanStatus


class ScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_scan(
        self,
        *,
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
    ) -> Scan:
        scan = Scan(
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
        self.session.add(scan)
        await self.session.flush()
        await self.session.refresh(scan)
        return scan

    async def get_by_id(self, scan_id: str) -> Scan | None:
        stmt = select(Scan).where(Scan.id == scan_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        *,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Scan]:
        stmt = (
            select(Scan)
            .where(Scan.user_id == user_id)
            .order_by(desc(Scan.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ScanRepository"]

