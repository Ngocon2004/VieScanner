from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.models.common import UTCDateTime


class ScanListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_id: str | None = None
    filename: str | None = None
    ocr_engine: str
    status: str
    duration_ms: int | None = None
    created_at: UTCDateTime


class ScanRead(ScanListItem):
    user_id: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    image_hash: str | None = None
    raw_data: dict | None = None
    confidences: dict | None = None
    error_code: str | None = None
    error_message: str | None = None


__all__ = ["ScanListItem", "ScanRead"]
