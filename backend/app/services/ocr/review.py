"""Đánh dấu kết quả cần người dùng xem lại: ảnh mặt sau, hoặc đọc được quá ít trường.

Trả về dạng `QualityIssue` mức "soft" để giao diện hiển thị chung với cảnh báo chất lượng ảnh,
thay vì để kết quả gần như trống vẫn báo "đã trích xuất" như bình thường.
"""

from __future__ import annotations

import re

from app.models.quality import QualityIssue
from app.services.ocr.address import fold
from app.services.ocr.interfaces import TextLine

TOTAL_FIELDS = 8
POOR_MAX_FIELDS = 3
_BACK_SIDE_WORDS = re.compile(r"idvnm|dacdiemnhandang|ngontro")
# Mặt trước thẻ Căn cước 2024 ("Số định danh cá nhân"), khác thẻ CCCD cũ ("Căn cước công dân", có "Quê quán").
_FRONT_2024_WORDS = re.compile(r"dinhdanh|personalident")
_OLD_CARD_WORDS = re.compile(r"congdan|citizen|quequan|placeoforigin")


def fields_read(confidences: dict[str, float]) -> int:
    return sum(1 for value in confidences.values() if value > 0)


def looks_like_back_side(lines: list[TextLine], confidences: dict[str, float]) -> bool:
    """Mặt sau CCCD: có MRZ hoặc nhãn "Đặc điểm nhân dạng"/"Ngón trỏ" và không có họ tên."""
    if confidences.get("full_name", 0) > 0:
        return False
    return any("<<" in line.text or _BACK_SIDE_WORDS.search(fold(line.text)) for line in lines)


def residence_on_back(lines: list[TextLine], confidences: dict[str, float]) -> bool:
    """Mặt trước thẻ Căn cước 2024 không in địa chỉ: nơi cư trú chỉ có ở mặt sau (chữ in hoặc QR)."""
    if confidences.get("residence", 0) > 0 or confidences.get("full_name", 0) <= 0:
        return False
    text = "".join(fold(line.text) for line in lines)
    return bool(_FRONT_2024_WORDS.search(text)) and not _OLD_CARD_WORDS.search(text)


def review_issues(
    confidences: dict[str, float],
    *,
    back_side: bool = False,
    mrz_read: bool = False,
    residence_on_back: bool = False,
) -> list[QualityIssue]:
    if back_side:
        # Mặt sau thẻ 2024 có in nơi cư trú: khi đã đọc được thì chỉ còn thiếu họ tên.
        missing = "họ tên" if confidences.get("residence", 0) > 0 else "họ tên và nơi thường trú"
        if mrz_read:
            message = f"Ảnh là mặt sau CCCD: các trường đọc được lấy từ dải MRZ. Tải ảnh mặt trước để có {missing}."
        else:
            message = f"Ảnh có vẻ là mặt sau CCCD. Tải ảnh mặt trước để có {missing}."
        return [QualityIssue(code="back_side", severity="soft", message=message)]
    if residence_on_back:
        return [
            QualityIssue(
                code="residence_on_back",
                severity="soft",
                message="Thẻ Căn cước mẫu 2024 in nơi cư trú ở mặt sau: tải thêm ảnh mặt sau để tự điền nơi cư trú.",
            )
        ]
    read = fields_read(confidences)
    if read <= POOR_MAX_FIELDS:
        return [
            QualityIssue(
                code="few_fields_read",
                severity="soft",
                message=f"Chỉ đọc được {read}/{TOTAL_FIELDS} trường. Kiểm tra lại ảnh hoặc nhập tay các trường còn thiếu.",
                metric=float(read),
                threshold=float(POOR_MAX_FIELDS),
            )
        ]
    return []


__all__ = ["POOR_MAX_FIELDS", "fields_read", "looks_like_back_side", "residence_on_back", "review_issues"]
