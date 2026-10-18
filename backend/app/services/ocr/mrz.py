"""Đọc dải MRZ mặt sau CCCD/Căn cước (ICAO 9303 TD1) từ các dòng chữ VietOCR đã đọc.

    Dòng 1: IDVNM <9 số cuối số CCCD><check> <12 số CCCD> ...
    Dòng 2: <YYMMDD ngày sinh><check><giới tính M/F><YYMMDD hạn dùng><check>VNM ...

VietOCR bỏ mất ký tự `<` và đôi khi đọc số thành chữ (0 -> O), nên không cắt theo vị trí cố định
mà tìm cụm ký tự có chữ số kiểm tra đúng (trọng số 7-3-1). Chỉ nhận cụm qua checksum, nên trường
MRZ tin cậy như QR. Đo trên 10 ảnh mặt sau thật: số CCCD đọc được ở 5 ảnh, ngày sinh/giới tính/hạn ở 4-5 ảnh,
không có giá trị sai.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.services.ocr.cccd_number import decode_cccd_number

_DIGIT_LIKE = "0-9OQDILZSBGT"
_TO_DIGIT = str.maketrans("OQDILZSBGT", "0001125867")
_WEIGHTS = (7, 3, 1)
_LINE1 = re.compile(r"(?=(\d{9})(\d)(\d{12}))")
# Quốc tịch VNM ngay sau hạn dùng: có trên cả 5 dòng 2 đọc được ở ảnh thật, chặn khớp nhầm với dòng chữ khác.
_LINE2 = re.compile(rf"(?=([{_DIGIT_LIKE}]{{7}})([MF])([{_DIGIT_LIKE}]{{7}})VNM)")


@dataclass(frozen=True, slots=True)
class MRZData:
    id_number: str | None = None
    dob: str | None = None
    gender: str | None = None
    expiry_date: str | None = None

    def to_fields(self) -> dict[str, str]:
        fields = {
            "id_number": self.id_number,
            "dob": self.dob,
            "gender": self.gender,
            "expiry_date": self.expiry_date,
        }
        found = {name: value for name, value in fields.items() if value}
        if found:
            found["nationality"] = "Việt Nam"
        return found


def _check_digit(digits: str) -> str:
    return str(sum(int(ch) * _WEIGHTS[i % 3] for i, ch in enumerate(digits)) % 10)


def _checked(group: str) -> str | None:
    """`group` = 6 số + 1 số kiểm tra; trả 6 số nếu checksum đúng."""
    value, check = group[:-1], group[-1]
    return value if _check_digit(value) == check else None


def _format_date(yymmdd: str, century: int) -> str | None:
    try:
        parsed = date(century * 100 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:]))
    except ValueError:
        return None
    return parsed.strftime("%d/%m/%Y")


def _normalize(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def read_mrz(texts: list[str], today: date | None = None) -> MRZData | None:
    today = today or date.today()
    id_number = None
    dates: tuple[str | None, str | None, str | None] | None = None
    for text in texts:
        line = _normalize(text)
        for doc, check, full in _LINE1.findall(line.translate(_TO_DIGIT)):
            # Số tài liệu = 9 số cuối của số CCCD: hai checksum độc lập, gần như không thể khớp nhầm.
            if id_number is None and _check_digit(doc) == check and full[3:] == doc and decode_cccd_number(full):
                id_number = full
        for birth, sex, expiry in _LINE2.findall(line):
            candidate = (_checked(birth.translate(_TO_DIGIT)), sex, _checked(expiry.translate(_TO_DIGIT)))
            if dates is None and (candidate[0] or candidate[2]):
                dates = candidate
    if id_number is None and dates is None:
        return None

    dob = gender = expiry = None
    if dates is not None:
        birth, sex, expiry_raw = dates
        info = decode_cccd_number(id_number)
        gender = info.gender if info is not None else ("Nam" if sex == "M" else "Nữ")
        if birth:
            if info is not None:
                century = info.birth_year // 100
            else:
                century = 20 if 2000 + int(birth[:2]) <= today.year else 19
            dob = _format_date(birth, century)
        if expiry_raw:
            expiry = _format_date(expiry_raw, 20)
    return MRZData(id_number=id_number, dob=dob, gender=gender, expiry_date=expiry)


__all__ = ["MRZData", "read_mrz"]
