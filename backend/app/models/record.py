from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.cccd import CCCDData


_DATE_RE = r"^(\d{2})/(\d{2})/(\d{4})$"


def _validate_date(value: str, *, field_name: str) -> str:
    from datetime import datetime as _dt
    import re

    if not re.match(_DATE_RE, value):
        raise ValueError(f"{field_name} must have DD/MM/YYYY format")
    _dt.strptime(value, "%d/%m/%Y")
    return value


class CCCDRecordBase(BaseModel):
    id_number: str = Field(min_length=12, max_length=12)
    full_name: str = Field(min_length=1, max_length=100)
    dob: str
    gender: str
    nationality: str = Field(min_length=1, max_length=50)
    origin: str = Field(min_length=1, max_length=200)
    residence: str = Field(min_length=1, max_length=200)
    expiry_date: str | None = None

    @field_validator("dob")
    @classmethod
    def _check_dob(cls, v: str) -> str:
        return _validate_date(v.strip(), field_name="dob")

    @field_validator("expiry_date")
    @classmethod
    def _check_expiry(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return _validate_date(v.strip(), field_name="expiry_date")


class CCCDRecordCreate(CCCDRecordBase):
    scan_id: str | None = None


class CCCDRecordUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    dob: str | None = None
    gender: str | None = None
    nationality: str | None = Field(default=None, min_length=1, max_length=50)
    origin: str | None = Field(default=None, min_length=1, max_length=200)
    residence: str | None = Field(default=None, min_length=1, max_length=200)
    expiry_date: str | None = None

    @field_validator("dob")
    @classmethod
    def _check_dob(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_date(v.strip(), field_name="dob")

    @field_validator("expiry_date")
    @classmethod
    def _check_expiry(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return _validate_date(v.strip(), field_name="expiry_date")


class CCCDRecordRead(CCCDRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scan_id: str | None = None
    user_id: str | None = None
    exported_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ExportRequest(BaseModel):
    # New shape
    data: CCCDData | None = None
    record_id: str | None = None
    scan_id: str | None = None

    # Legacy shape compatibility
    id_number: str | None = None
    full_name: str | None = None
    dob: str | None = None
    gender: str | None = None
    nationality: str | None = None
    origin: str | None = None
    residence: str | None = None
    expiry_date: str | None = None


__all__ = [
    "CCCDRecordCreate",
    "CCCDRecordUpdate",
    "CCCDRecordRead",
    "ExportRequest",
]
