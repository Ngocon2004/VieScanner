"""Đọc QR code mặt trước CCCD gắn chip (2021+).

CCCD gắn chip in sẵn 1 QR code mã hoá thông tin theo định dạng 7 trường ngăn
bởi dấu `|`:

    <số CCCD>|<số CMND cũ>|<họ tên>|<ngày sinh>|<giới tính>|<nơi thường trú>|<ngày cấp>

Trong đó ngày sinh / ngày cấp ở dạng `ddmmyyyy` (8 chữ số, không dấu phân cách).

Module dùng `cv2.QRCodeDetector` của OpenCV (đã là dependency sẵn cho image
quality / pipeline) nên **không thêm thư viện mới**. QR cho độ chính xác gần
tuyệt đối với các trường nó cung cấp; pipeline OCR vẫn chạy để:
  - Bù các trường QR không có: quốc tịch, quê quán (origin), hạn dùng.
  - Làm fallback khi ảnh không có QR / QR đọc lỗi.

Tất cả hàm degrade gracefully: thiếu OpenCV, ảnh hỏng, hay QR không đúng định
dạng CCCD đều trả `None` để pipeline tiếp tục bằng OCR thuần.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.logging import logger

if TYPE_CHECKING:
    import numpy as np


_ID_NUMBER_RE = re.compile(r"^\d{12}$")
_MIN_QR_PARTS = 6  # số CCCD..nơi thường trú; ngày cấp (phần 7) là tuỳ chọn.

# Trùng placeholder của RealFieldExtractor để UX nhất quán (FE highlight đỏ).
_UNKNOWN_PLACEHOLDER = "(không nhận dạng được)"


@dataclass(slots=True)
class CCCDQRData:
    """Dữ liệu giải mã từ QR mặt trước CCCD (đã chuẩn hoá về schema CCCDData)."""

    id_number: str
    full_name: str
    dob: str  # dd/mm/yyyy
    gender: str  # "Nam" | "Nữ"
    residence: str
    issue_date: str | None = None  # dd/mm/yyyy; chưa map vào CCCDData hiện tại.
    raw: str = ""

    def to_field_overrides(self) -> dict[str, str]:
        """Các trường QR map trực tiếp sang CCCDData (ưu tiên ghi đè OCR)."""
        return {
            "id_number": self.id_number,
            "full_name": self.full_name,
            "dob": self.dob,
            "gender": self.gender,
            "residence": self.residence,
        }

    def to_full_fields(self) -> dict[str, str]:
        """Bộ field đầy đủ cho CCCDData khi CHỈ dựa vào QR (OCR fail).

        Các trường QR không cung cấp được điền mặc định an toàn: quốc tịch
        "Việt Nam" (mặc định cho CCCD), quê quán để placeholder cho user rà soát.
        Hạn dùng (expiry_date) để trống vì QR không chứa.
        """
        fields = self.to_field_overrides()
        fields["nationality"] = "Việt Nam"
        fields["origin"] = _UNKNOWN_PLACEHOLDER
        return fields


def _normalize_qr_date(value: str) -> str | None:
    """`ddmmyyyy` -> `dd/mm/yyyy`. Trả None nếu không phải ngày hợp lệ."""
    digits = value.strip()
    if len(digits) != 8 or not digits.isdigit():
        return None
    formatted = f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"
    try:
        datetime.strptime(formatted, "%d/%m/%Y")
    except ValueError:
        return None
    return formatted


def _normalize_gender(value: str) -> str | None:
    """Chuẩn hoá giới tính về 'Nam'/'Nữ'; trả None nếu không nhận ra."""
    v = value.strip()
    if v in ("Nam", "Nữ"):
        return v
    low = v.lower()
    if low == "nam":
        return "Nam"
    if low in ("nữ", "nu"):
        return "Nữ"
    return None


def parse_cccd_qr_payload(payload: str | None) -> CCCDQRData | None:
    """Parse chuỗi giải mã QR -> `CCCDQRData`.

    Trả None nếu payload không đúng định dạng CCCD (để pipeline dùng OCR).
    """
    if not payload:
        return None
    parts = payload.split("|")
    if len(parts) < _MIN_QR_PARTS:
        return None

    id_number = parts[0].strip()
    if not _ID_NUMBER_RE.match(id_number):
        return None

    full_name = parts[2].strip()
    dob = _normalize_qr_date(parts[3])
    gender = _normalize_gender(parts[4])
    residence = parts[5].strip()
    issue_date = _normalize_qr_date(parts[6]) if len(parts) > 6 else None

    # Cần đủ các trường cốt lõi mới coi là QR CCCD hợp lệ.
    if not (full_name and dob and gender and residence):
        return None

    return CCCDQRData(
        id_number=id_number,
        full_name=full_name,
        dob=dob,
        gender=gender,
        residence=residence,
        issue_date=issue_date,
        raw=payload,
    )


def read_cccd_qr(image: "np.ndarray") -> CCCDQRData | None:
    """Detect + decode QR mặt trước CCCD từ ảnh BGR (numpy).

    Trả `CCCDQRData` nếu đọc được QR đúng định dạng CCCD, ngược lại `None`.
    """
    try:
        import cv2  # type: ignore[import-untyped]
    except Exception as exc:  # noqa: BLE001 - thiếu OpenCV -> bỏ qua QR.
        logger.debug("QR reader: OpenCV không khả dụng ({})", exc)
        return None

    if image is None or getattr(image, "ndim", 0) < 2 or getattr(image, "size", 0) == 0:
        return None

    try:
        detector = cv2.QRCodeDetector()
        data, _points, _straight = detector.detectAndDecode(image)
        parsed = parse_cccd_qr_payload(data)
        if parsed is not None:
            return parsed

        # Fallback: ảnh nhiều mã / khó -> thử detect nhiều QR.
        ok, decoded_info, _pts, _qr = detector.detectAndDecodeMulti(image)
        if ok and decoded_info:
            for decoded in decoded_info:
                parsed = parse_cccd_qr_payload(decoded)
                if parsed is not None:
                    return parsed
    except Exception as exc:  # noqa: BLE001 - decode lỗi -> để OCR xử lý.
        logger.debug("QR detect/decode thất bại: {}", exc)
        return None

    return None


__all__ = ["CCCDQRData", "parse_cccd_qr_payload", "read_cccd_qr"]
