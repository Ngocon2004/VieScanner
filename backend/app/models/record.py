from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.models.common import UTCDateTime

from app.models.cccd import _ID_NUMBER_RE, _VALID_GENDERS, CCCDData, _parse_date_strict
from app.services.ocr.cccd_number import decode_cccd_number
from app.services.ocr.placeholders import FIELD_PLACEHOLDERS, UNKNOWN_TEXT


def _check_field(name: str, v: str | None) -> str | None:
    """Áp đúng luật của CCCDData cho 1 trường (None = không đổi khi PATCH).

    Dữ liệu sai phải bị chặn ở 422 thay vì vỡ 500 khi dựng CCCDData/lưu DB.
    """
    if v is None:
        return None
    v = v.strip()
    if name == "expiry_date":
        return _parse_date_strict(v, field_name=name) if v else None
    if name == "dob":
        return _parse_date_strict(v, field_name=name)
    if name == "id_number" and not _ID_NUMBER_RE.match(v):
        raise ValueError("id_number must contain exactly 12 digits")
    if name == "gender" and v not in _VALID_GENDERS:
        raise ValueError("gender must be Nam or Nữ")
    if not v:
        raise ValueError("field cannot be empty")
    return v


_ALL_FIELDS = ("id_number", "full_name", "dob", "gender", "nationality", "origin", "residence", "expiry_date")


class _RecordFields(BaseModel):
    id_number: str = Field(min_length=12, max_length=12)
    full_name: str = Field(min_length=1, max_length=100)
    dob: str
    gender: str
    nationality: str = Field(min_length=1, max_length=50)
    origin: str = Field(min_length=1, max_length=200)
    residence: str = Field(min_length=1, max_length=200)
    expiry_date: str | None = None


class CCCDRecordBase(_RecordFields):
    @field_validator(*_ALL_FIELDS)
    @classmethod
    def _check(cls, v: str | None, info: ValidationInfo) -> str | None:
        return _check_field(info.field_name, v)


class CCCDRecordCreate(CCCDRecordBase):
    scan_id: str | None = None


class CCCDRecordUpdate(BaseModel):
    id_number: str | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    dob: str | None = None
    gender: str | None = None
    nationality: str | None = Field(default=None, min_length=1, max_length=50)
    origin: str | None = Field(default=None, min_length=1, max_length=200)
    residence: str | None = Field(default=None, min_length=1, max_length=200)
    expiry_date: str | None = None

    @field_validator(*_ALL_FIELDS)
    @classmethod
    def _check(cls, v: str | None, info: ValidationInfo) -> str | None:
        return _check_field(info.field_name, v)


class CCCDRecordRead(_RecordFields):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scan_id: str | None = None
    user_id: str | None = None
    exported_at: UTCDateTime | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime


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


_LIST_FIELDS = ("full_name", "id_number", "dob", "gender", "residence")


class ExportListRow(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    id_number: str
    dob: str
    gender: str
    residence: str = Field(min_length=1, max_length=200)
    scan_ids: list[str] = Field(default_factory=list, max_length=10)

    @field_validator(*_LIST_FIELDS)
    @classmethod
    def _check(cls, v: str, info: ValidationInfo) -> str:
        v = _check_field(info.field_name, v)
        if v in (UNKNOWN_TEXT, FIELD_PLACEHOLDERS["id_number"]):
            raise ValueError("field was not recognized, enter it manually")
        if info.field_name == "full_name" and any(ch.isdigit() for ch in v):
            raise ValueError("full_name cannot contain digits")
        if info.field_name == "dob" and datetime.strptime(v, "%d/%m/%Y").date() > date.today():
            raise ValueError("dob cannot be in the future")
        return v

    @model_validator(mode="after")
    def _match_id_number(self) -> "ExportListRow":
        # Số CCCD mã hóa thế kỷ + giới tính + năm sinh: lệch nhau nghĩa là có trường sai, không được xuất.
        info = decode_cccd_number(self.id_number)
        if info is None:
            raise ValueError("id_number is not a valid CCCD number")
        if info.gender != self.gender:
            raise ValueError("gender does not match id_number")
        if int(self.dob[-4:]) != info.birth_year:
            raise ValueError("dob year does not match id_number")
        return self


class ExportListRequest(BaseModel):
    rows: list[ExportListRow] = Field(min_length=1, max_length=1000)


__all__ = [
    "CCCDRecordCreate",
    "ExportListRequest",
    "ExportListRow",
    "CCCDRecordUpdate",
    "CCCDRecordRead",
    "ExportRequest",
]
