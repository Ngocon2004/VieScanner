"""Pydantic schemas for CCCD data and API responses."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


_ID_NUMBER_RE = re.compile(r"^\d{12}$")
_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_VALID_GENDERS = {"Nam", "Nữ"}


def _parse_date_strict(value: str, *, field_name: str) -> str:
    match = _DATE_RE.match(value)
    if not match:
        raise ValueError(f"{field_name} must follow DD/MM/YYYY")
    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid date") from exc
    return value


class CCCDData(BaseModel):
    id_number: str = Field(..., description="12-digit CCCD number")
    full_name: str = Field(..., min_length=1, max_length=100)
    dob: str = Field(..., description="Date of birth DD/MM/YYYY")
    gender: str = Field(..., description="Nam or Nu/Nữ")
    nationality: str = Field(..., min_length=1, max_length=50)
    origin: str = Field(..., min_length=1, max_length=200)
    residence: str = Field(..., min_length=1, max_length=200)
    expiry_date: str | None = Field(default=None, description="DD/MM/YYYY")

    @field_validator("id_number")
    @classmethod
    def _check_id(cls, v: str) -> str:
        v = v.strip()
        if not _ID_NUMBER_RE.match(v):
            raise ValueError("id_number must contain exactly 12 digits")
        return v

    @field_validator("dob")
    @classmethod
    def _check_dob(cls, v: str) -> str:
        return _parse_date_strict(v.strip(), field_name="dob")

    @field_validator("expiry_date")
    @classmethod
    def _check_expiry(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return _parse_date_strict(v.strip(), field_name="expiry_date")

    @field_validator("gender")
    @classmethod
    def _check_gender(cls, v: str) -> str:
        v = v.strip()
        if v not in _VALID_GENDERS:
            raise ValueError("gender must be Nam or Nữ")
        return v

    @field_validator("full_name", "nationality", "origin", "residence")
    @classmethod
    def _strip_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("field cannot be empty")
        return v


class CCCDExtractResponse(BaseModel):
    data: CCCDData
    confidences: dict[str, float] = Field(default_factory=dict)
    scan_id: str | None = None

    @field_validator("confidences")
    @classmethod
    def _normalize_confidences(cls, v: dict[str, float]) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for key, value in v.items():
            normalized[key] = max(0.0, min(1.0, float(value)))
        return normalized


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    details: list | None = None
