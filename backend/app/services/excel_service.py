"""Excel export service – sinh file .xlsx từ CCCDData."""

from __future__ import annotations

import io

import pandas as pd

from app.models.cccd import CCCDData


def generate_excel(data: CCCDData) -> bytes:
    """Convert CCCDData → bytes của file Excel (.xlsx) sẵn sàng download."""
    # Chuyển dữ liệu sang DataFrame
    df = pd.DataFrame([data.model_dump()])

    # Đổi tên cột cho đẹp
    df.columns = [
        "Số CCCD", "Họ và tên", "Ngày sinh", "Giới tính",
        "Quốc tịch", "Quê quán", "Nơi thường trú", "Ngày hết hạn"
    ]

    # Tạo stream byte để lưu file Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Thông tin CCCD')

    return output.getvalue()


__all__ = ["generate_excel"]
