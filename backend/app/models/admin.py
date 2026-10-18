from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import UTCDateTime


class OverviewTotals(BaseModel):
    scans: int
    succeeded: int
    failed: int
    median_duration_ms: int | None
    p90_duration_ms: int | None
    users: int
    new_users: int
    exported_scans: int
    corrections: int
    active_jobs: int


class DailyScans(BaseModel):
    date: str
    success: int
    failed: int


class ErrorCount(BaseModel):
    code: str
    count: int


class FieldQuality(BaseModel):
    field: str
    read: int
    read_rate: float
    low_confidence: int
    corrected: int
    corrected_rate: float


class AdminOverview(BaseModel):
    days: int
    totals: OverviewTotals
    daily: list[DailyScans]
    errors: list[ErrorCount]
    fields: list[FieldQuality]
    jobs: dict[str, int]


class AdminSystem(BaseModel):
    ocr_engine: str
    engine_ready: bool
    pipeline_version: str
    queue_size: int
    concurrency: int
    qr_enabled: bool
    cache_enabled: bool
    cache_ttl_hours: float
    scan_retention_days: int
    job_retention_days: int
    auth_required: bool


class AdminUser(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: UTCDateTime
    scans: int
    exported_scans: int
    last_scan_at: UTCDateTime | None


class AdminUserUpdate(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


class AdminScanItem(BaseModel):
    id: str
    created_at: UTCDateTime
    user_email: str | None
    status: str
    ocr_engine: str
    duration_ms: int | None
    error_code: str | None
    id_number_masked: str | None
    fields_read: int = Field(ge=0)
    low_confidence_fields: int = Field(ge=0)
    from_job: bool


__all__ = [
    "AdminOverview",
    "AdminScanItem",
    "AdminSystem",
    "AdminUser",
    "AdminUserUpdate",
    "DailyScans",
    "ErrorCount",
    "FieldQuality",
    "OverviewTotals",
]
