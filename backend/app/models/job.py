from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.models.common import UTCDateTime

from app.models.cccd import BatchItemResult


class JobItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seq: int
    upload_index: int
    filename: str | None = None
    container_filename: str | None = None
    page_number: int | None = None
    status: str
    scan_id: str | None = None
    result: BatchItemResult | None = None


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    status: str
    total_items: int
    processed_items: int
    succeeded_items: int
    failed_items: int
    created_at: UTCDateTime
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None


class JobRead(JobSummary):
    items: list[JobItemRead]


__all__ = ["JobItemRead", "JobRead", "JobSummary"]
