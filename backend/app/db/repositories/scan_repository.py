from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cccd_record import CCCDRecord
from app.db.models.correction import Correction
from app.db.models.job import JobItem
from app.db.models.scan import Scan, ScanStatus


class ScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_scan(
        self,
        *,
        id: str | None = None,
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
        job_id: str | None = None,
    ) -> Scan:
        scan = Scan(
            user_id=user_id,
            request_id=request_id,
            job_id=job_id,
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
        # Cho phép pre-generate id (M4): caller tạo UUID trước để trả `scan_id`
        # trong response rồi ghi scan ở background. None -> dùng default của model.
        if id is not None:
            scan.id = id
        self.session.add(scan)
        await self.session.flush()
        await self.session.refresh(scan)
        return scan

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Xóa scan có `created_at < cutoff`. Trả về số scan đã xóa (M5).

        Xử lý bảng con tường minh để an toàn cả khi DB không bật FK cascade
        (vd SQLite mặc định): xóa `corrections` liên quan + gỡ liên kết
        `cccd_records` (scan_id -> NULL) trước khi xóa scan. Caller tự commit.
        """
        old_ids = select(Scan.id).where(Scan.created_at < cutoff)
        await self.session.execute(
            delete(Correction).where(Correction.scan_id.in_(old_ids))
        )
        await self.session.execute(
            update(CCCDRecord)
            .where(CCCDRecord.scan_id.in_(old_ids))
            .values(scan_id=None)
        )
        await self.session.execute(
            update(JobItem).where(JobItem.scan_id.in_(old_ids)).values(scan_id=None)
        )
        result = await self.session.execute(
            delete(Scan).where(Scan.created_at < cutoff)
        )
        return result.rowcount or 0

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

    async def get_latest_success_by_image_hash(
        self,
        *,
        image_hash: str,
        user_id: str | None,
        ocr_engine: str | None = None,
        ttl_seconds: int = 0,
    ) -> Scan | None:
        stmt = (
            select(Scan)
            .where(
                Scan.image_hash == image_hash,
                Scan.user_id == user_id,
                Scan.status == ScanStatus.SUCCESS,
                Scan.raw_data.is_not(None),
            )
            .order_by(desc(Scan.created_at))
            .limit(1)
        )
        if ocr_engine:
            # Khớp đúng nhãn engine + phiên bản pipeline: đổi engine/logic OCR thì bỏ qua kết quả cũ.
            # Không nhận dòng ":cache" để TTL tính từ lần OCR thật, không tự gia hạn qua mỗi lần trúng cache.
            stmt = stmt.where(Scan.ocr_engine == ocr_engine)
        if ttl_seconds > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
            stmt = stmt.where(Scan.created_at >= cutoff)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ScanRepository"]

