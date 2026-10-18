"""M5 – Scan retention: dọn dẹp scan cũ để bảng `scans` không phình.

Mỗi request OCR (kể cả cache hit) ghi 1 row vào `scans`. Nếu để lâu dài bảng sẽ
phình. Job này xóa scan cũ hơn `SCAN_RETENTION_DAYS` ngày, chạy lúc startup và
lặp lại theo chu kỳ. Tắt bằng `SCAN_RETENTION_DAYS=0` (mặc định).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.repositories.scan_repository import ScanRepository
from app.db.session import SessionLocal


async def purge_old_scans_once() -> int:
    """Xóa scan cũ hơn ngưỡng 1 lần. Trả về số scan đã xóa (0 nếu tắt/lỗi)."""
    days = settings.scan_retention_days
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with SessionLocal() as session:
        try:
            deleted = await ScanRepository(session).delete_older_than(cutoff)
            await session.commit()
            if deleted:
                logger.info(
                    "Retention: purged {} scan(s) older than {} day(s).", deleted, days
                )
            return deleted
        except Exception as exc:  # noqa: BLE001 – không để job làm chết app.
            await session.rollback()
            logger.warning("Retention purge skipped: {}", exc)
            return 0


async def retention_loop() -> None:
    """Chạy `purge_old_scans_once` định kỳ tới khi task bị cancel (lúc shutdown)."""
    interval_seconds = max(1, settings.scan_retention_interval_hours) * 3600
    while True:
        await purge_old_scans_once()
        await asyncio.sleep(interval_seconds)


__all__ = ["purge_old_scans_once", "retention_loop"]
