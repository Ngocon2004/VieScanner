"""Kiểm tra quyền gắn một scan vào hồ sơ/corrections (dùng chung cho export và records)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
from app.db.models.scan import Scan
from app.db.repositories.scan_repository import ScanRepository


async def attachable_scan(db: AsyncSession, scan_id: str | None, user_id: str | None) -> Scan | None:
    """Scan không tồn tại (đã bị dọn) thì bỏ qua; scan của người khác thì chặn."""
    if not scan_id:
        return None
    scan = await ScanRepository(db).get_by_id(scan_id)
    if scan is not None and scan.user_id and scan.user_id != user_id:
        raise AuthorizationError("Bạn không có quyền dùng lượt quét này.", code="scan_forbidden")
    return scan


__all__ = ["attachable_scan"]
