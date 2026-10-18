"""Excel export service – sinh file .xlsx từ CCCDData."""

from __future__ import annotations

import io

import pandas as pd

from app.models.cccd import CCCDData
from app.models.record import ExportListRow

_COLUMNS = {
    "id_number": "Số CCCD",
    "full_name": "Họ và tên",
    "dob": "Ngày sinh",
    "gender": "Giới tính",
    "nationality": "Quốc tịch",
    "origin": "Quê quán",
    "residence": "Nơi thường trú",
    "expiry_date": "Ngày hết hạn",
}
_LIST_COLUMNS = {
    "full_name": ("Họ và tên", 28),
    "id_number": ("Số CCCD", 16),
    "dob": ("Ngày sinh", 12),
    "gender": ("Giới tính", 10),
    "residence": ("Nơi thường trú", 70),
}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: object) -> object:
    # Chống formula injection: dữ liệu OCR/người dùng sửa bắt đầu bằng "=" sẽ bị Excel chạy như công thức.
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def generate_excel(data: CCCDData) -> bytes:
    """Convert CCCDData → bytes của file Excel (.xlsx) sẵn sàng download."""
    row = data.model_dump()
    df = pd.DataFrame([{label: _safe_cell(row.get(field)) for field, label in _COLUMNS.items()}])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Thông tin CCCD")

    return output.getvalue()


def generate_excel_list(rows: list[ExportListRow]) -> bytes:
    """Danh sách nhiều người -> 1 sheet, mỗi người 1 dòng, cột STT đầu tiên."""
    records = [
        {"STT": n, **{label: _safe_cell(getattr(row, field)) for field, (label, _) in _LIST_COLUMNS.items()}}
        for n, row in enumerate(rows, start=1)
    ]
    df = pd.DataFrame(records, columns=["STT", *(label for label, _ in _LIST_COLUMNS.values())])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Danh sách CCCD")
        sheet = writer.sheets["Danh sách CCCD"]
        sheet.freeze_panes = "A2"
        widths = [6, *(width for _, width in _LIST_COLUMNS.values())]
        for col, width in zip("ABCDEF", widths, strict=True):
            sheet.column_dimensions[col].width = width
        # Số CCCD có số 0 ở đầu: ép kiểu Text để Excel không đổi thành số và mất số 0.
        for (cell,) in sheet.iter_rows(min_row=2, min_col=3, max_col=3):
            cell.number_format = "@"

    return output.getvalue()


__all__ = ["generate_excel", "generate_excel_list"]
