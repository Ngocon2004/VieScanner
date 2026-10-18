"""Sửa địa danh trong quê quán / nơi thường trú bằng danh mục hành chính (ý tưởng dictionary-guided
recognition, CVPR 2021): OCR hay sai dấu/chữ ở tên tỉnh, huyện, xã nhưng các tên này là tập đóng.

So khớp từ cuối địa chỉ lên: tỉnh -> huyện thuộc tỉnh đó -> xã thuộc huyện đó, so trên chuỗi đã bỏ dấu.
Chỉ thay khi khớp gần chắc chắn và không mơ hồ; phần không khớp giữ nguyên chữ OCR.
Danh mục gồm cả 63 tỉnh cũ (địa chỉ in trên CCCD cấp trước 07/2025) lẫn 34 tỉnh sau sáp nhập.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

_DATA = Path(__file__).parent / "resources" / "admin_units_vn.json"
_MIN_SCORE = 88
# Tên ngắn (Ba Vì, Hà Nam...) sai 1 ký tự đã thành tên khác -> phải khớp tuyệt đối.
_SHORT_KEY_LEN = 5
_TYPE_CANONICAL = {
    "tinh": "Tỉnh", "thanhpho": "Thành phố", "huyen": "Huyện", "quan": "Quận", "thixa": "Thị xã",
    "xa": "Xã", "phuong": "Phường", "thitran": "Thị trấn", "dackhu": "Đặc khu",
}
# Viết tắt giữ nguyên như OCR đọc (không chuẩn hóa thành tên đầy đủ).
_TYPE_ABBREVIATIONS = frozenset({"tp", "tx", "tt"})
_PROVINCE_ALIASES = {"Thừa Thiên Huế": "Huế"}
# OCR hay đọc khoảng trắng trong tên loại đơn vị nhiều chữ thành dấu chấm ("Dân.Phố"); viết tắt 1 chữ
# như "TP.", "P.5" không thuộc danh sách nên giữ nguyên.
_MULTIWORD_UNITS = ("Tổ Dân Phố", "Tổ Dân Cư", "Khu Dân Cư", "Khu Phố", "Thị Trấn", "Thị Xã", "Thành Phố")
_UNIT_SEPARATOR_RE = re.compile(
    "|".join(r"\b" + r"\s*[.\s]\s*".join(f"({w})" for w in unit.split()) + r"\b" for unit in _MULTIWORD_UNITS),
    re.IGNORECASE,
)


# Dấu chấm dính giữa số nhà và tên đường ("12/34.Lê Lợi") cũng là khoảng trắng đọc sai;
# "P.5", "Q.1", "TP.HCM" có chữ đứng trước dấu chấm nên không bị đụng.
_NUMBER_DOT_WORD_RE = re.compile(r"(?<=\d)\.(?=[^\W\d_]{2,})")


def _fix_unit_separators(text: str) -> str:
    text = _NUMBER_DOT_WORD_RE.sub(" ", unicodedata.normalize("NFC", text))
    return _UNIT_SEPARATOR_RE.sub(lambda m: " ".join(g for g in m.groups() if g), text)


def fold(text: str) -> str:
    """Bỏ dấu, chữ thường, chỉ giữ a-z0-9: khóa so khớp chịu được lỗi dấu và khoảng trắng."""
    nfd = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "d"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower())


@dataclass(frozen=True, slots=True)
class AddressMatch:
    text: str
    has_province: bool
    corrected_parts: int
    # Các phần không khớp danh mục (số nhà, thôn, tên đường...): chữ OCR chưa được kiểm chứng.
    unverified: str = ""


@dataclass(frozen=True, slots=True)
class _Units:
    provinces: dict[str, str]
    districts: dict[str, dict[str, str]]
    wards_by_district: dict[tuple[str, str], dict[str, str]]
    wards_by_province: dict[str, dict[str, str]]


@lru_cache(maxsize=1)
def _units() -> _Units:
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    provinces: dict[str, str] = {}
    districts: dict[str, dict[str, str]] = {}
    wards_by_district: dict[tuple[str, str], dict[str, str]] = {}
    wards_by_province: dict[str, dict[str, str]] = {}
    for name, prov in raw["legacy"].items():
        provinces[name] = name
        districts[name] = {d: d for d in prov["districts"]}
        for d_name, dist in prov["districts"].items():
            wards_by_district[(name, d_name)] = {w: w for _, w in dist["wards"]}
    for name, prov in raw["from_2025"].items():
        provinces.setdefault(name, name)
        wards_by_province[name] = {w: w for _, w in prov["wards"]}
    for alias, name in _PROVINCE_ALIASES.items():
        provinces[alias] = alias
        districts[alias] = districts.get(name, {})
        for (p, d), wards in list(wards_by_district.items()):
            if p == name:
                wards_by_district[(alias, d)] = wards
    return _Units(provinces, districts, wards_by_district, wards_by_province)


def _split_type(part: str) -> tuple[str, str]:
    """Tách tiền tố loại đơn vị ("Huyện", "TP.", "Thị trấn"...) khỏi tên."""
    words = re.sub(r"^(TP|TX|TT)\.(?=\S)", r"\1. ", part, flags=re.IGNORECASE).split()
    for n in (2, 1):
        head = fold(" ".join(words[:n]))
        if len(words) > n and head in _TYPE_CANONICAL:
            return _TYPE_CANONICAL[head], " ".join(words[n:])
        if len(words) > n and head in _TYPE_ABBREVIATIONS:
            return " ".join(words[:n]), " ".join(words[n:])
    return "", part


def _best(name: str, candidates: dict[str, str]) -> str | None:
    if not candidates or not name:
        return None
    key = fold(name)
    by_key: dict[str, list[str]] = {}
    for canonical in candidates:
        by_key.setdefault(fold(canonical), []).append(canonical)
    hit = process.extractOne(key, list(by_key), scorer=fuzz.ratio)
    if hit is None:
        return None
    match_key, score, _ = hit
    if score < _MIN_SCORE or (len(match_key) <= _SHORT_KEY_LEN and score < 100):
        return None
    options = by_key[match_key]
    if len(options) == 1:
        return options[0]
    # Cùng khóa không dấu (Tân Thạnh / Tân Thành): chọn theo dấu OCR đọc được, hòa thì không sửa.
    scored = sorted(((fuzz.ratio(name, o), o) for o in options), reverse=True)
    return scored[0][1] if scored[0][0] > scored[1][0] else None


def match_address(text: str) -> AddressMatch:
    # Ghép dòng có sẵn dấu phẩy cuối tạo phần rỗng ("Hải,, Tỉnh"): bỏ để không ra ", ,".
    parts = [p.strip() for p in _fix_unit_separators(text).split(",") if p.strip()]
    units = _units()
    out = list(parts)
    verified: set[int] = set()
    province = district = None
    levels = ("province", "district", "ward")
    for level, idx in zip(levels, range(len(parts) - 1, -1, -1), strict=False):
        prefix, name = _split_type(parts[idx])
        if level == "province":
            canonical = _best(name, units.provinces)
            province = canonical
        elif level == "district":
            canonical = _best(name, units.districts.get(province, {}))
            if canonical is None:
                # Địa chỉ sau 07/2025 không còn cấp huyện: xã nằm ngay trước tỉnh.
                canonical = _best(name, units.wards_by_province.get(province, {}))
                if canonical is not None:
                    out[idx] = f"{prefix} {canonical}".strip()
                    verified.add(idx)
                break
            district = canonical
        else:
            canonical = _best(name, units.wards_by_district.get((province, district), {}))
        if canonical is None:
            break
        out[idx] = f"{prefix} {canonical}".strip()
        verified.add(idx)
    return AddressMatch(
        text=", ".join(out),
        has_province=province is not None,
        corrected_parts=sum(out[i] != parts[i] for i in verified),
        unverified=", ".join(part for i, part in enumerate(out) if i not in verified),
    )


def preload_admin_units() -> None:
    _units()


def ends_with_province(text: str) -> bool:
    last = text.rsplit(",", 1)[-1]
    return _best(_split_type(last)[1], _units().provinces) is not None


__all__ = ["AddressMatch", "ends_with_province", "fold", "match_address", "preload_admin_units"]
