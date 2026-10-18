"""Lưu tạm bytes ảnh của job trên đĩa trong lúc chờ xử lý.

Ảnh CCCD là dữ liệu cá nhân: chỉ nằm ở đây tới khi job xong hoặc quá `JOB_TTL_MINUTES`.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from app.core.config import settings


def _root() -> Path:
    return Path(settings.job_tmp_dir)


def _item_path(job_id: str, item_id: str) -> Path:
    return _root() / job_id / f"{item_id}.bin"


def upload_path(job_id: str, upload_index: int) -> Path:
    """File gốc người dùng gửi; item ảnh/trang đọc từ đây cho tới khi được chuẩn bị riêng (`write_item`)."""
    return _root() / job_id / f"upload-{upload_index}.bin"


def write_item(job_id: str, item_id: str, data: bytes) -> None:
    path = _item_path(job_id, item_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_item(job_id: str, item_id: str) -> bytes | None:
    path = _item_path(job_id, item_id)
    return path.read_bytes() if path.exists() else None


def delete_item(job_id: str, item_id: str) -> None:
    _item_path(job_id, item_id).unlink(missing_ok=True)


def delete_job(job_id: str) -> None:
    shutil.rmtree(_root() / job_id, ignore_errors=True)


def purge_expired(
    max_age_seconds: float,
    active_job_ids: frozenset[str] = frozenset(),
    active_max_age_seconds: float = 24 * 3600,
) -> list[str]:
    """Xóa ảnh tạm quá hạn. Job còn trong hàng đợi được giữ (hàng đợi dài có thể chờ quá TTL),
    nhưng không quá `active_max_age_seconds` để job kẹt không giữ ảnh CCCD trên đĩa mãi."""
    root = _root()
    if not root.exists():
        return []
    now = time.time()
    removed: list[str] = []
    for job_dir in root.iterdir():
        if not job_dir.is_dir():
            continue
        age = now - job_dir.stat().st_mtime
        limit = active_max_age_seconds if job_dir.name in active_job_ids else max_age_seconds
        if age > limit:
            shutil.rmtree(job_dir, ignore_errors=True)
            removed.append(job_dir.name)
    return removed


__all__ = ["delete_item", "delete_job", "purge_expired", "read_item", "upload_path", "write_item"]
