from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.cccd import CCCDData


def _valid_payload() -> dict[str, str]:
    return {
        "id_number": "001202000123",
        "full_name": "NGUYEN VAN A",
        "dob": "01/01/2002",
        "gender": "Nam",
        "nationality": "Viet Nam",
        "origin": "Quan 1, TP HCM",
        "residence": "123 Le Loi, Quan 1, TP HCM",
        "expiry_date": "01/01/2030",
    }


def test_cccd_data_valid_payload_passes() -> None:
    data = CCCDData(**_valid_payload())
    assert data.id_number == "001202000123"
    assert data.gender == "Nam"


def test_cccd_data_rejects_invalid_id_number() -> None:
    payload = _valid_payload()
    payload["id_number"] = "12345"

    with pytest.raises(ValidationError):
        CCCDData(**payload)


def test_cccd_data_rejects_invalid_dob_format() -> None:
    payload = _valid_payload()
    payload["dob"] = "2002-01-01"

    with pytest.raises(ValidationError):
        CCCDData(**payload)


def test_cccd_data_rejects_invalid_gender() -> None:
    payload = _valid_payload()
    payload["gender"] = "Khac"

    with pytest.raises(ValidationError):
        CCCDData(**payload)


def test_cccd_data_normalizes_empty_expiry_to_none() -> None:
    payload = _valid_payload()
    payload["expiry_date"] = ""

    data = CCCDData(**payload)
    assert data.expiry_date is None
