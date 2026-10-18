"""Tests cho M4 (ghi scan qua BackgroundTasks) + M5 (retention service)."""

from __future__ import annotations

import pytest
from fastapi import BackgroundTasks

from app.controllers import ocr_controller
from app.core.config import settings
from app.db.models.scan import ScanStatus
from app.services.retention import purge_old_scans_once


def test_schedule_scan_adds_background_task() -> None:
    """M4: `_schedule_scan` thêm 1 background task ghi scan với id pre-generated."""
    background_tasks = BackgroundTasks()
    ocr_controller._schedule_scan(
        background_tasks,
        scan_id="abc-123",
        user_id=None,
        request_id="req-1",
        filename="card.png",
        mime_type="image/png",
        size_bytes=100,
        image_hash="h" * 64,
        ocr_engine="mock",
        status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000123"},
        confidences={"id_number": 0.99},
        error_code=None,
        error_message=None,
        duration_ms=12,
    )

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is ocr_controller._persist_scan_bg
    # scan_id được map sang tham số `id` của create_scan.
    assert task.kwargs["id"] == "abc-123"
    assert task.kwargs["ocr_engine"] == "mock"
    assert task.kwargs["status"] == ScanStatus.SUCCESS
    # Không lẫn key `scan_id` (đã đổi tên thành `id`).
    assert "scan_id" not in task.kwargs


@pytest.mark.asyncio
async def test_purge_old_scans_disabled_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """M5: retention tắt (days<=0) -> no-op, không chạm DB."""
    monkeypatch.setattr(settings, "scan_retention_days", 0)
    assert await purge_old_scans_once() == 0
