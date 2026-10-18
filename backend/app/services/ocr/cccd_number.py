"""Giải mã cấu trúc số CCCD 12 chữ số (Thông tư 07/2016/TT-BCA, giữ nguyên theo Luật Căn cước 2023).

    [3 số mã tỉnh nơi đăng ký khai sinh][1 số thế kỷ + giới tính][2 số cuối năm sinh][6 số ngẫu nhiên]

Số thế kỷ + giới tính: 0/1 = thế kỷ 20 nam/nữ, 2/3 = thế kỷ 21 nam/nữ, 4/5 = thế kỷ 22...
Mã tỉnh là bảng 63 tỉnh cũ; số đã cấp không đổi sau sáp nhập tỉnh 2025.

Extractor dùng để chọn đúng chuỗi 12 số và kiểm tra chéo với ngày sinh/giới tính OCR đọc được:
lệch nhau nghĩa là ít nhất 1 trường bị đọc sai, nên các trường đó phải được người dùng rà soát.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

PROVINCE_CODES: frozenset[str] = frozenset(
    f"{code:03d}"
    for code in (
        1, 2, 4, 6, 8, 10, 11, 12, 14, 15, 17, 19, 20, 22, 24, 25, 26, 27, 30, 31, 33,
        34, 35, 36, 37, 38, 40, 42, 44, 45, 46, 48, 49, 51, 52, 54, 56, 58, 60, 62, 64,
        66, 67, 68, 70, 72, 74, 75, 77, 79, 80, 82, 83, 84, 86, 87, 89, 91, 92, 93, 94,
        95, 96,
    )
)


@dataclass(frozen=True, slots=True)
class CCCDNumberInfo:
    province_code: str
    gender: str  # "Nam" | "Nữ"
    birth_year: int


def decode_cccd_number(value: str | None, today: date | None = None) -> CCCDNumberInfo | None:
    """Trả thông tin mã hoá trong số CCCD, hoặc None nếu số không thể là CCCD hợp lệ."""
    if not value or len(value) != 12 or not value.isdigit():
        return None
    province, century_gender, yy = value[:3], int(value[3]), int(value[4:6])
    if province not in PROVINCE_CODES:
        return None
    birth_year = (19 + century_gender // 2) * 100 + yy
    if birth_year > (today or date.today()).year:
        return None
    return CCCDNumberInfo(
        province_code=province,
        gender="Nữ" if century_gender % 2 else "Nam",
        birth_year=birth_year,
    )


__all__ = ["PROVINCE_CODES", "CCCDNumberInfo", "decode_cccd_number"]
