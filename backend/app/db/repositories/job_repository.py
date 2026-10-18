from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.scan import Scan
from app.db.models.job import (
    TERMINAL_ITEM_STATUSES,
    Job,
    JobItem,
    JobItemStatus,
    JobSource,
    JobStatus,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: str | None,
        source: JobSource,
        ocr_engine: str,
        items: list[dict],
        job_id: str | None = None,
    ) -> Job:
        job = Job(
            **({"id": job_id} if job_id else {}),
            user_id=user_id,
            source=source,
            ocr_engine=ocr_engine,
            status=JobStatus.QUEUED,
            total_items=len(items),
            processed_items=0,
            succeeded_items=0,
            failed_items=0,
        )
        job.items = [JobItem(seq=seq, **item) for seq, item in enumerate(items)]
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: str, *, with_items: bool = True) -> Job | None:
        stmt = select(Job).where(Job.id == job_id)
        if with_items:
            stmt = stmt.options(selectinload(Job.items))
        result = await self.session.execute(stmt.execution_options(populate_existing=True))
        return result.scalar_one_or_none()

    async def get_item(self, item_id: str) -> JobItem | None:
        result = await self.session.execute(select(JobItem).where(JobItem.id == item_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, *, user_id: str, limit: int, offset: int) -> list[Job]:
        stmt = (
            select(Job)
            .where(Job.user_id == user_id)
            .order_by(desc(Job.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def queued_item_ids(self) -> list[tuple[str, str]]:
        stmt = (
            select(JobItem.job_id, JobItem.id)
            .join(Job)
            .where(JobItem.status == JobItemStatus.QUEUED, Job.status != JobStatus.CANCELLED)
            .order_by(Job.created_at, JobItem.seq)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]

    async def active_job_ids(self) -> list[str]:
        stmt = select(Job.id).where(Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]))
        return list((await self.session.execute(stmt)).scalars())

    async def reset_processing_items(self) -> int:
        result = await self.session.execute(
            update(JobItem)
            .where(JobItem.status == JobItemStatus.PROCESSING)
            .values(status=JobItemStatus.QUEUED)
        )
        return result.rowcount or 0

    async def cancel_queued_items(self, job_id: str) -> None:
        await self.session.execute(
            update(JobItem)
            .where(JobItem.job_id == job_id, JobItem.status == JobItemStatus.QUEUED)
            .values(status=JobItemStatus.CANCELLED)
        )

    async def refresh_progress(self, job_id: str) -> Job | None:
        """Tính lại bộ đếm từ trạng thái item (idempotent, an toàn khi nhiều worker)."""
        # Session dùng autoflush=False: phải flush để truy vấn đếm thấy thay đổi chưa ghi.
        await self.session.flush()
        rows = (
            await self.session.execute(
                select(JobItem.status, func.count())
                .where(JobItem.job_id == job_id)
                .group_by(JobItem.status)
            )
        ).all()
        counts = {status: n for status, n in rows}
        job = await self.get(job_id, with_items=False)
        if job is None:
            return None

        # Worker có thể thay 1 ảnh nhiều thẻ bằng nhiều item: tổng phải đếm lại, không cố định lúc tạo.
        job.total_items = sum(counts.values())
        job.processed_items = sum(counts.get(s, 0) for s in TERMINAL_ITEM_STATUSES)
        job.succeeded_items = counts.get(JobItemStatus.DONE, 0)
        job.failed_items = counts.get(JobItemStatus.REJECTED, 0) + counts.get(JobItemStatus.FAILED, 0)

        if job.status == JobStatus.CANCELLED:
            if counts.get(JobItemStatus.PROCESSING, 0) == 0 and job.finished_at is None:
                job.finished_at = _now()
        elif job.processed_items >= job.total_items:
            if job.succeeded_items == job.total_items:
                job.status = JobStatus.COMPLETED
            elif job.succeeded_items == 0:
                job.status = JobStatus.FAILED
            else:
                job.status = JobStatus.PARTIAL
            job.finished_at = job.finished_at or _now()
        elif job.processed_items > 0 or counts.get(JobItemStatus.PROCESSING, 0) > 0:
            job.status = JobStatus.PROCESSING
            job.started_at = job.started_at or _now()
        await self.session.flush()
        return job

    async def replace_item(self, job_id: str, item_id: str, items: list[dict]) -> list[JobItem]:
        """Xóa 1 item và thêm các item thay thế (mỗi thẻ của ảnh nhiều thẻ) trong cùng transaction."""
        # Khóa dòng job (Postgres) để 2 worker tách thẻ cùng job không cấp trùng seq; SQLite vốn ghi tuần tự.
        await self.session.execute(select(Job.id).where(Job.id == job_id).with_for_update())
        await self.session.execute(delete(JobItem).where(JobItem.id == item_id))
        next_seq = (
            await self.session.execute(select(func.max(JobItem.seq)).where(JobItem.job_id == job_id))
        ).scalar_one_or_none()
        start = 0 if next_seq is None else next_seq + 1
        created = [JobItem(job_id=job_id, seq=start + n, **item) for n, item in enumerate(items)]
        self.session.add_all(created)
        await self.session.flush()
        return created

    async def delete(self, job_id: str) -> None:
        await self.session.execute(update(Scan).where(Scan.job_id == job_id).values(job_id=None))
        await self.session.execute(delete(JobItem).where(JobItem.job_id == job_id))
        await self.session.execute(delete(Job).where(Job.id == job_id))

    async def delete_older_than(self, cutoff: datetime) -> list[str]:
        ids = list(
            (
                await self.session.execute(
                    select(Job.id).where(Job.created_at < cutoff)
                )
            ).scalars().all()
        )
        for job_id in ids:
            await self.delete(job_id)
        return ids


__all__ = ["JobRepository"]
