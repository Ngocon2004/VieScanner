"""Giá trị giữ chỗ cho trường không đọc được.

Giá trị này qua được validator của `CCCDData` và luôn đi kèm confidence 0, nên frontend
tô đỏ trường đó và người dùng phải nhập tay. Extractor, QR và pipeline dùng chung để
nhất quán.
"""

from __future__ import annotations

UNKNOWN_TEXT = "(không nhận dạng được)"

FIELD_PLACEHOLDERS: dict[str, str] = {
    "id_number": "000000000000",
    "full_name": UNKNOWN_TEXT,
    "dob": "01/01/2000",
    "gender": "Nam",
    "nationality": "Việt Nam",
    "origin": UNKNOWN_TEXT,
    "residence": UNKNOWN_TEXT,
}

__all__ = ["FIELD_PLACEHOLDERS", "UNKNOWN_TEXT"]
