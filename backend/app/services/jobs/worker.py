"""Job worker: xử lý nền từng ảnh của job qua hàng đợi asyncio trong cùng process.

Trạng thái nằm trong DB (jobs/job_items), bytes ảnh nằm ở `tmp_store`, nên khi server
khởi động lại worker khôi phục được các item còn dang dở.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import logger
from app.db import session as db_session
from app.db.models.job import TERMINAL_JOB_STATUSES, JobItemStatus, JobStatus
from app.db.repositories.job_repository import JobRepository
from app.db.repositories.scan_repository import ScanRepository
from app.models.cccd import BatchItemResult, CCCDExtractResponse
from app.services.extraction import CRASH_MESSAGE, make_upload, process_upload
from app.services.intake import IntakeItem, IntakeLimitError, prepare_item
from app.services.jobs import tmp_store
from app.services.ocr_engine import OCREngine, get_ocr_engine
from app.utils.image import detect_image_mime

_ITEM_STATUS_BY_RESULT = {
    "extracted": JobItemStatus.DONE,
    "rejected": JobItemStatus.REJECTED,
    "ocr_failed": JobItemStatus.FAILED,
}


def _default_session_factory() -> async_sessionmaker[AsyncSession]:
    return db_session.SessionLocal


@dataclass(frozen=True, slots=True)
class _ItemRef:
    id: str
    seq: int
    upload_index: int
    filename: str | None
    container_filename: str | None
    page_number: int | None
    job_id: str = ""


def _prepare(job_id: str, ref: _ItemRef) -> list[IntakeItem] | None:
    """Ảnh cần OCR của item (CPU-bound, chạy trong thread). None = file tạm đã bị dọn vì quá hạn.

    Thẻ tách từ ảnh nhiều thẻ có sẵn ảnh riêng; item khác chuẩn bị từ file gốc (render trang, đổi HEIC, tách thẻ).
    """
    planned = IntakeItem(
        ref.upload_index, ref.filename, container_filename=ref.container_filename, page_number=ref.page_number
    )
    data = tmp_store.read_item(job_id, ref.id)
    if data is not None:
        return [replace(planned, mime_type=detect_image_mime(data) or "image/jpeg", contents=data)]
    path = tmp_store.upload_path(job_id, ref.upload_index)
    if not path.exists():
        return None
    return prepare_item(planned, path)


class JobWorker:
    def __init__(
        self,
        *,
        session_factory: Callable[[], async_sessionmaker[AsyncSession]] = _default_session_factory,
        engine_provider: Callable[[], OCREngine] = get_ocr_engine,
        concurrency: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.engine_provider = engine_provider
        self.concurrency = max(1, concurrency or settings.ocr_max_concurrency)
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._seen: dict[str, dict[str, CCCDExtractResponse]] = {}

    def qsize(self) -> int:
        return self._queue.qsize()

    def enqueue(self, job_id: str, item_id: str) -> None:
        self._queue.put_nowait((job_id, item_id))

    async def start(self) -> None:
        await self.recover()
        self._tasks = [asyncio.create_task(self._run()) for _ in range(self.concurrency)]
        self._tasks.append(asyncio.create_task(self._cleanup_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def join(self) -> None:
        await self._queue.join()

    async def recover(self) -> None:
        try:
            async with self.session_factory()() as session:
                repo = JobRepository(session)
                reset = await repo.reset_processing_items()
                pending = await repo.queued_item_ids()
                await session.commit()
        except Exception as exc:  # noqa: BLE001 – DB chưa migrate không được làm chết app.
            logger.warning("job recovery skipped: {}", exc)
            return
        for job_id, item_id in pending:
            self.enqueue(job_id, item_id)
        if pending or reset:
            logger.info("job recovery | requeued={} reset_processing={}", len(pending), reset)

    async def _run(self) -> None:
        while True:
            job_id, item_id = await self._queue.get()
            try:
                await self.process_item(job_id, item_id)
            except Exception:  # noqa: BLE001
                logger.exception("job item crashed | job={} item={}", job_id, item_id)
            finally:
                self._queue.task_done()

    async def process_item(self, job_id: str, item_id: str) -> None:
        factory = self.session_factory()
        async with factory() as session:
            repo = JobRepository(session)
            job = await repo.get(job_id, with_items=False)
            item = await repo.get_item(item_id)
            if job is None or item is None or item.status != JobItemStatus.QUEUED:
                if job is None or job.status in TERMINAL_JOB_STATUSES:
                    self._seen.pop(job_id, None)
                return
            if job.status == JobStatus.CANCELLED:
                item.status = JobItemStatus.CANCELLED
                await session.commit()
                tmp_store.delete_item(job_id, item_id)
                return
            item.status = JobItemStatus.PROCESSING
            await repo.refresh_progress(job_id)
            await session.commit()
            user_id = job.user_id
            ref = _ItemRef(
                item.id, item.seq, item.upload_index, item.filename, item.container_filename, item.page_number,
                job_id,
            )

        # Item đã ở PROCESSING: mọi lỗi từ đây phải kết thúc bằng trạng thái cuối,
        # nếu không item kẹt mãi và client poll vô hạn.
        try:
            prepared = await asyncio.to_thread(_prepare, job_id, ref)
            if prepared is not None and len(prepared) > 1:
                await self._split(job_id, ref, prepared)
                return
            result, scan_fields = await self._extract(ref, prepared, user_id)
        except Exception:  # noqa: BLE001
            logger.exception("job item crashed | job={} item={}", job_id, item_id)
            result = BatchItemResult(
                index=ref.seq, filename=ref.filename, accepted=True, status="ocr_failed",
                error_code="ocr_engine_crashed", error_message=CRASH_MESSAGE,
            )
            scan_fields = None

        scan_id = await self._persist_scan(job_id, scan_fields) if scan_fields else None
        if result.status == "extracted":
            result.scan_id = scan_id

        async with factory() as session:
            repo = JobRepository(session)
            item = await repo.get_item(item_id)
            if item is None:
                return
            item.status = _ITEM_STATUS_BY_RESULT[result.status]
            item.scan_id = scan_id
            item.result = result.model_dump(mode="json")
            job = await repo.refresh_progress(job_id)
            await session.commit()
            finished = job is None or job.status in TERMINAL_JOB_STATUSES

        tmp_store.delete_item(job_id, item_id)
        if finished:
            tmp_store.delete_job(job_id)
            self._seen.pop(job_id, None)

    async def _extract(
        self, ref: _ItemRef, prepared: list[IntakeItem] | None, user_id: str | None
    ) -> tuple[BatchItemResult, dict | None]:
        if prepared is None:
            return BatchItemResult(
                index=ref.seq, filename=ref.filename, accepted=False, status="rejected",
                error_code="file_expired",
                error_message="Ảnh tạm đã hết hạn trước khi được xử lý. Vui lòng tải lên lại.",
            ), None
        image = prepared[0]
        if image.error_code or image.contents is None:
            return BatchItemResult(
                index=ref.seq, filename=ref.filename, accepted=False, status="rejected",
                error_code=image.error_code, error_message=image.error_message,
            ), None
        upload = make_upload(ref.filename, image.mime_type or "image/jpeg", image.contents)
        engine = await asyncio.to_thread(self.engine_provider)
        async with self.session_factory()() as session:
            outcome = await process_upload(
                index=ref.seq,
                upload=upload,
                engine=engine,
                repo=ScanRepository(session),
                seen=self._seen.setdefault(ref.job_id, {}),
                user_id=user_id,
            )
        return outcome.result, outcome.scan

    async def _split(self, job_id: str, ref: _ItemRef, cards: list[IntakeItem]) -> None:
        """Ảnh/trang nhiều thẻ: thay item bằng 1 item mỗi thẻ. Ảnh thẻ ghi đĩa trước, DB đổi trong 1 transaction
        nên dừng giữa chừng thì lần chạy lại tách lại từ file gốc, không sinh item trùng."""
        async with self.session_factory()() as session:
            repo = JobRepository(session)
            job = await repo.get(job_id, with_items=False)
            # Giới hạn số item mỗi job như lúc nhận file: thẻ vượt giới hạn được báo lỗi, không OCR.
            capacity = settings.job_max_items - (job.total_items - 1 if job else 0)
            rows = []
            for n, card in enumerate(cards):
                card_id = str(uuid4())
                if n < capacity and card.contents is not None:
                    tmp_store.write_item(job_id, card_id, card.contents)
                rows.append({
                    "id": card_id,
                    "upload_index": card.upload_index,
                    "filename": card.filename,
                    "container_filename": card.container_filename,
                    "page_number": card.page_number,
                    "status": JobItemStatus.QUEUED if n < capacity else JobItemStatus.REJECTED,
                })
            created = await repo.replace_item(job_id, ref.id, rows)
            for row in created:
                if row.status == JobItemStatus.REJECTED:
                    row.result = BatchItemResult(
                        index=row.seq, filename=row.filename, accepted=False, status="rejected",
                        error_code=IntakeLimitError.code,
                        error_message=f"Tổng số ảnh/trang vượt giới hạn {settings.job_max_items} mỗi job.",
                    ).model_dump(mode="json")
            await repo.refresh_progress(job_id)
            await session.commit()
        queued = [row.id for row in created if row.status == JobItemStatus.QUEUED]
        for card_id in queued:
            self.enqueue(job_id, card_id)
        logger.info("job item split | job={} cards={} queued={}", job_id, len(created), len(queued))

    async def _persist_scan(self, job_id: str, fields: dict) -> str | None:
        try:
            async with self.session_factory()() as session:
                scan = await ScanRepository(session).create_scan(
                    job_id=job_id, request_id=None, **fields
                )
                await session.commit()
                return scan.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("job scan logging skipped: {}", exc)
            return None

    async def cleanup_once(self) -> None:
        try:
            async with self.session_factory()() as session:
                active = frozenset(await JobRepository(session).active_job_ids())
        except Exception as exc:  # noqa: BLE001 – không đọc được DB thì vẫn dọn theo TTL (ưu tiên xóa ảnh CCCD).
            logger.warning("job cleanup: cannot read active jobs: {}", exc)
            active = frozenset()
        for job_id in tmp_store.purge_expired(settings.job_ttl_minutes * 60, active):
            logger.info("job tmp expired | job={}", job_id)
        if settings.job_retention_days <= 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.job_retention_days)
        try:
            async with self.session_factory()() as session:
                removed = await JobRepository(session).delete_older_than(cutoff)
                await session.commit()
            if removed:
                logger.info("job retention | removed={}", len(removed))
        except Exception as exc:  # noqa: BLE001
            logger.warning("job retention skipped: {}", exc)

    async def _cleanup_loop(self) -> None:
        interval = max(1, settings.job_cleanup_interval_minutes) * 60
        while True:
            await self.cleanup_once()
            await asyncio.sleep(interval)


__all__ = ["JobWorker"]
