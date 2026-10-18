"""Sinh `app/services/ocr/resources/admin_units_vn.json` (danh mục tỉnh/huyện/xã) cho bước sửa địa danh.

Nguồn: bảng `admin_units_legacy` và `admin_units` trong `dataset.db` của gói
`vietnamadminunits` (MIT, https://github.com/tranngocminhhieu/vietnamadminunits), dữ liệu gốc
từ danh mục hành chính của Tổng cục Thống kê.

Chạy (không cần cài gói vào venv):
    pip install --no-deps --target <tmp> vietnamadminunits==1.0.4
    python scripts/build_admin_units.py <tmp>/vietnamadminunits/data/dataset.db
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "services" / "ocr" / "resources" / "admin_units_vn.json"


def main(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    legacy: dict[str, dict] = {}
    rows = conn.execute(
        "select province, provinceShort, districtType, districtShort, wardType, wardShort "
        "from admin_units_legacy order by provinceCode, districtCode, wardCode"
    )
    for province, p_short, d_type, d_short, w_type, w_short in rows:
        p_type = province[: -len(p_short)].strip()
        prov = legacy.setdefault(p_short, {"type": p_type, "districts": {}})
        dist = prov["districts"].setdefault(d_short, {"type": d_type, "wards": []})
        if w_short:
            dist["wards"].append([w_type or "", w_short])

    current: dict[str, dict] = {}
    rows = conn.execute(
        "select province, provinceShort, wardType, wardShort from admin_units order by provinceCode, wardCode"
    )
    for province, p_short, w_type, w_short in rows:
        prov = current.setdefault(p_short, {"type": province[: -len(p_short)].strip(), "wards": []})
        prov["wards"].append([w_type or "", w_short])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "vietnamadminunits 1.0.4 (MIT) – Tổng cục Thống kê",
        "legacy": legacy,
        "from_2025": current,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} | legacy provinces={len(legacy)} | 2025 provinces={len(current)}")


if __name__ == "__main__":
    main(sys.argv[1])
