"""Extractor – stage ⑤ của pipeline.

- `MockExtractor`: giả định detector + recognizer cấp đúng 8 dòng theo thứ tự
  chuẩn của CCCD, map 1-1 sang field name.
- `RealFieldExtractor`: rule-based extraction từ list `TextLine` → CCCDData.

Chiến lược 3 tầng (theo độ tin cậy giảm dần):

1. **Global regex** (confidence cao 0.95-1.0):
   - `id_number`: chuỗi 12 số đầu tiên giải mã được theo cấu trúc CCCD (`cccd_number`).
   - `dob` / `expiry_date`: `dd/mm/yyyy` có lịch hợp lệ. Ngày sớm nhất khớp năm sinh trong số
     CCCD = DOB, muộn nhất = expiry.
   - `gender`: standalone "Nam" hoặc "Nữ" (không lấy "Nam" trong "Việt Nam"); không đọc được
     thì suy từ số CCCD.
   - Số CCCD lệch giới tính/năm sinh -> hạ confidence các trường liên quan để user rà soát.

Độ tin cậy mỗi trường = min(độ tin cậy của luật, xác suất VietOCR của dòng nguồn).

2. **Label-based** (confidence 0.85):
   - Quét từng dòng tìm label ("Họ và tên", "Quê quán", "Nơi thường trú", ...).
   - Value lấy từ phần sau dấu ":" trên cùng dòng, hoặc dòng kế tiếp nếu không có.
   - Hỗ trợ song ngữ Vietnamese/English; tolerance OCR dấu/typo nhẹ.

3. **Fuzzy fallback** (confidence 0.85):
   - Nationality: fuzzy match "Việt Nam" với rapidfuzz (handle "Viet Nam", "VietNam", ...).

4. **Default placeholder** (confidence 0.0):
   - Field không tìm được → fill placeholder pass schema validation.
   - Frontend xem confidence để hiển thị màu đỏ + auto-focus user edit (Phase 3).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from datetime import datetime

from app.core.logging import logger
from app.services.ocr.address import ends_with_province, match_address
from app.services.ocr.cccd_number import CCCDNumberInfo, decode_cccd_number
from app.services.ocr.interfaces import BBox, ExtractionResult, TextLine
from app.services.ocr.placeholders import FIELD_PLACEHOLDERS


def _normalize(text: str) -> str:
    """Lowercase + bỏ dấu tiếng Việt → ascii để robust với OCR errors.

    Vd: "Nơi thường trúi" → "noi thuong trui"
        "Place of residene" → "place of residene"
    """
    nfd = unicodedata.normalize("NFD", text)
    no_accent = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Đặc biệt: đ/Đ không thuộc combining mark → cần map thủ công.
    no_accent = no_accent.replace("đ", "d").replace("Đ", "d")
    return no_accent.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Mock
# ─────────────────────────────────────────────────────────────────────────────


# Thứ tự field tương ứng với MockDetector + MockRecognizer.
_MOCK_FIELD_ORDER: tuple[str, ...] = (
    "id_number",
    "full_name",
    "dob",
    "gender",
    "nationality",
    "origin",
    "residence",
    "expiry_date",
)


class MockExtractor:
    """Map từng dòng vào field theo thứ tự cố định (giả định MockDetector)."""

    def extract(self, lines: list[TextLine]) -> ExtractionResult:
        fields: dict[str, str] = {}
        confidences: dict[str, float] = {}
        for name, line in zip(_MOCK_FIELD_ORDER, lines, strict=False):
            fields[name] = line.text
            confidences[name] = _line_confidence(1.0, line)
        logger.debug("MockExtractor.extract | fields={}", list(fields.keys()))
        return ExtractionResult(fields=fields, confidences=confidences)


# ─────────────────────────────────────────────────────────────────────────────
# Real – rule-based extractor
# ─────────────────────────────────────────────────────────────────────────────


# Regex cho global extraction.
_ID12_RE = re.compile(r"(?<!\d)(\d{12})(?!\d)")
# OCR hay tách số CCCD bằng dấu cách/chấm ("001 202 000 123").
_ID_SEPARATORS_RE = re.compile(r"(?<=\d)[\s.](?=\d)")
_LONG_DIGITS_RE = re.compile(r"\d{13,}")
# "Nam" trong "Việt Nam" (quốc tịch) không phải giới tính.
_GENDER_NAM_RE = re.compile(r"(?<![Vv]i[eệ]t\s)\bNam\b")
# Dòng địa chỉ dài hay chứa "Nam"/"Nữ" (Hà Nam, Quảng Nam...): chỉ đoán giới tính từ dòng ngắn.
_GENDER_FALLBACK_MAX_LEN = 20
_DATE_RE = re.compile(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})")
# Dưới ngưỡng 0.6 của CCCDForm: trường được tô cảnh báo nhưng vẫn giữ giá trị OCR đọc được.
_SUSPECT_CONFIDENCE = 0.5
# Ký tự yếu nhất của giá trị dưới ngưỡng này -> cảnh báo dù xác suất trung bình dòng cao. Đo trên 61 thẻ thật
# (đáp án từ QR và danh mục hành chính): bắt 5/6 từ địa danh đọc sai (trung bình dòng: 0/6), họ tên sai
# mà không bị cảnh báo 3 -> 1, không cảnh báo nhầm trường đúng nào.
_WEAK_CHAR_CONFIDENCE = 0.7
_WORD_RE = re.compile(r"\w+")
# Hạn thẻ in đúng sinh nhật năm đủ 14/25/40/60 tuổi (Luật Căn cước 2023; CCCD cũ 25/40/60).
_EXPIRY_AGES = frozenset({14, 25, 40, 60})

# VietOCR batch trả xác suất cao cả khi đọc sai, nên trường chữ không bao giờ bị cảnh báo
# (eval 63 ảnh: 0 cảnh báo dù có lỗi). Các dấu hiệu bất thường theo nội dung dưới đây bù vào;
# chạy trên text đã bỏ dấu (`_normalize`).
_NAME_FOREIGN_LETTERS_RE = re.compile(r"[fjwz]")  # tên tiếng Việt không dùng; thường là dính "Full name".
_ODD_CHARS_RE = re.compile(r"[^\w\s,./\-']")
_LABEL_LEFTOVER_RE = re.compile(
    r"\bho\s*(?:va\s*)?ten\b|\bfull\s*name|\bque\s*quan\b|\borigin|\bthuong\s*tru|\bresiden|\bplace\s*of\b"
    r"|\bnoi\s*(?:thuong|cu)\b"
)
_ADMIN_UNIT_RE = re.compile(
    r"\b(?:xa|phuong|thi\s*tran|huyen|quan|thi\s*xa|thanh\s*pho|tinh|tp|thon|ap|ban|to|khu\s*pho"
    r"|xom|khom|duong|so|kp|tt)\b"
)
_NAME_WORDS_RANGE = (2, 7)
# Họ tên trên CCCD in hoa toàn bộ; nhãn và các dòng khác là chữ thường/hoa đầu từ.
_NAME_UPPER_RATIO = 0.8


def _normalized_dates(text: str) -> set[str]:
    return {f"{int(d):02d}/{int(m):02d}/{y}" for d, m, y in _DATE_RE.findall(text)}

# Label patterns – chạy trên text đã normalize (ascii lowercase, no diacritics).
# Mỗi pattern dùng substring tối thiểu UNIQUE giữa các label, tolerant với
# OCR errors phổ biến (extra char, missing char nhỏ).
_LABEL_PATTERNS: dict[str, re.Pattern] = {
    # "Số / No.:" – chỉ "no." hoặc "so:" / "so/no" để tránh false positive với từ khác
    "id_number": re.compile(r"\b(?:so\s*/\s*no|no\.|so\s*:)", re.IGNORECASE),
    # "Họ và tên / Full name"
    "full_name": re.compile(r"ho\s*(?:va\s*)?ten|full\s*name", re.IGNORECASE),
    # "Ngày sinh / Date of birth"
    "dob": re.compile(r"ngay.*sinh|date\s*of\s*birth", re.IGNORECASE),
    # "Giới tính / Sex"
    "gender": re.compile(r"gioi\s*tinh|\bsex\b", re.IGNORECASE),
    # "Quốc tịch / Nationality"
    "nationality": re.compile(r"quoc\s*tich|nationality", re.IGNORECASE),
    # "Quê quán / Place of origin"
    "origin": re.compile(r"que\s*quan|nguyen\s*quan|place\s*of\s*origin", re.IGNORECASE),
    # "Nơi thường trú / Place of residence" – match Vietnamese hoặc English.
    # Pattern English greedy match cả "residence", "residenc", "residene"
    # (OCR thường rớt 1 ký tự cuối) → tránh trailing "ene" trong value.
    # Vietnamese: "thuong" + chữ "trú" bị đọc sai thành trui/trai/tro/tra (14/63 ảnh thật để sót chữ này
    # vào đầu địa chỉ).
    # Thẻ Căn cước 2024 in "Nơi cư trú" ở mặt sau (mặt trước không có địa chỉ); ảnh thật OCR ra "Nơi cut trú".
    "residence": re.compile(
        r"thuong\s*tr[a-z]{0,2}(?![a-z])|noi\s*thuong|noi\s*cu\s*t*\s*tru|place\s*of\s*residenc?e?",
        re.IGNORECASE,
    ),
    # Chỉ để làm mốc kết thúc địa chỉ trên mặt sau thẻ 2024 ("Nơi đăng ký khai sinh / Place of birth").
    "birth_registration": re.compile(r"dang\s*ky\s*khai\s*sinh|place\s*of\s*birth", re.IGNORECASE),
    # "Có giá trị đến / Date of expiry"
    "expiry_date": re.compile(
        r"co\s*gia\s*tri|date\s*of\s*expiry|han\s*su\s*dung",
        re.IGNORECASE,
    ),
}

# Nhãn tiếng Anh "Place of residence/origin" OCR đọc sai không còn khớp nhãn ("Pace clionce",
# "place cinsidonce12/3a", "pince of msad"): bỏ ở đầu giá trị địa chỉ. Chỉ chạy trên text đã normalize.
_PLACE_LABEL_TAIL = re.compile(
    r"[\s/|:;.,-]*(?:p[a-z]{2,4}(?:\s*o[a-z]?(?![a-z]))?\s*[a-z]{0,10}?nce?(?![a-z])"
    r"|p[a-z]{2,4}\s+o[fr]\s+[a-z]{2,10}(?![a-z]))[\s/|:;.,-]*"
)


def _label_end(pattern: re.Pattern, norm_text: str, start: int = 0) -> int:
    """Vị trí kết thúc xa nhất của các match nối/chồng nhau bắt đầu từ match đầu tiên sau `start`, 0 nếu không khớp.

    `finditer` bỏ match chồng nhau: "noi thuong tru" chỉ ra "noi thuong" và để sót "tru" vào giá trị.
    """
    m = pattern.search(norm_text, start)
    if m is None:
        return 0
    end, pos = m.end(), m.start() + 1
    while (nxt := pattern.search(norm_text, pos)) is not None and nxt.start() <= end:
        end, pos = max(end, nxt.end()), nxt.start() + 1
    return end


def _drop_place_label(text: str) -> str:
    """Bỏ nhãn "Place of ..." đọc sai ở đầu giá trị địa chỉ (text phải là NFC để vị trí khớp bản normalize)."""
    m = _PLACE_LABEL_TAIL.match(_normalize(text))
    return text[m.end():] if m else text


# Sau khi match label, value thường nằm sau ":" hoặc "/<English>:". VietOCR hay đọc ":" thành ";"
# ("Full name;") -> coi như nhau, nếu không phần ";" bị lấy làm giá trị rỗng và mất dòng tên bên dưới.
_VALUE_AFTER_COLON = re.compile(r"[:;]\s*(.+)$")


def _line_confidence(rule_confidence: float, *lines: TextLine) -> float:
    """Độ tin cậy trường = min(độ tin cậy luật trích xuất, xác suất OCR của các dòng nguồn).

    Dòng không có xác suất (None, VietOCR beamsearch) không kéo điểm xuống.
    """
    probs = [line.recognizer_confidence for line in lines if line.recognizer_confidence is not None]
    return min([rule_confidence, *probs])


def _weakest_char(text: str, sources: list[TextLine]) -> float | None:
    """Xác suất ký tự thấp nhất của các từ trong `text`, tra theo vị trí từ đó ở các dòng nguồn.

    Từ không còn nguyên văn trong dòng nguồn (đã được danh mục sửa) bị bỏ qua; None nếu không tra được từ nào.
    """
    weakest: float | None = None
    for word in set(_WORD_RE.findall(text)):
        pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)")
        for line in sources:
            chars = line.char_confidences
            if chars is None or len(chars) != len(line.text):
                continue
            for m in pattern.finditer(line.text):
                low = min(chars[m.start() : m.end()])
                weakest = low if weakest is None else min(weakest, low)
    return weakest


def _implausible_text(field: str, value: str) -> bool:
    """Giá trị họ tên/quê quán/thường trú có dấu hiệu đọc sai hoặc cắt sai."""
    plain = _normalize(value)
    words = value.split()
    if _ODD_CHARS_RE.search(value) or _LABEL_LEFTOVER_RE.search(plain):
        return True
    if field == "full_name":
        low, high = _NAME_WORDS_RANGE
        return bool(re.search(r"\d", value) or _NAME_FOREIGN_LETTERS_RE.search(plain)) or not low <= len(words) <= high
    if len(words) < 2:
        return True
    if field == "origin":
        return bool(re.search(r"\d", value))
    # Quê quán hay ghi gọn "Hưng Hà, Thái Bình" nên chỉ nơi thường trú bắt buộc có đơn vị hành chính.
    return field == "residence" and not _ADMIN_UNIT_RE.search(plain)


def _same_row_right(label: BBox, other: BBox) -> bool:
    """`other` là nửa sau của dòng `label` bị detector cắt: cùng hàng, ở nửa phải, chồng hoặc sát mép phải.

    Box cách xa hơn nửa chiều cao dòng là cột khác (vd ngày hết hạn) -> không ghép.
    """
    overlap = min(label.ymax, other.ymax) - max(label.ymin, other.ymin)
    height = min(label.ymax - label.ymin, other.ymax - other.ymin)
    return (
        height > 0
        and overlap >= 0.5 * height
        and other.xmin >= label.xmin + 0.5 * (label.xmax - label.xmin)
        and other.xmin <= label.xmax + 0.5 * height
    )


class RealFieldExtractor:
    """Rule-based extractor cho CCCD layout 2016/2020."""

    _DEFAULTS = FIELD_PLACEHOLDERS

    def __init__(self, *, fuzzy_threshold: int = 80) -> None:
        self.fuzzy_threshold = fuzzy_threshold

    def extract(self, lines: list[TextLine]) -> ExtractionResult:
        # NFC: cắt chuỗi theo vị trí tìm được trên bản bỏ dấu chỉ đúng khi mỗi ký tự có dấu
        # là 1 code point; VietOCR đôi khi trả dạng tổ hợp (NFD).
        cleaned = [
            replace(line, text=unicodedata.normalize("NFC", line.text))
            for line in lines
            if line.text and line.text.strip()
        ]
        if not cleaned:
            logger.warning("RealFieldExtractor: 0 input lines.")
            return self._fill_defaults({}, {})

        fields: dict[str, str] = {}
        confidences: dict[str, float] = {}

        # 1. Global regex extractions ────────────────────────────────────
        self._extract_id_number(cleaned, fields, confidences)
        id_info = decode_cccd_number(fields.get("id_number"))
        self._extract_dates(cleaned, fields, confidences, id_info)
        self._extract_gender(cleaned, fields, confidences)
        self._cross_check_id(fields, confidences, id_info)

        # 2. Label-based extractions ─────────────────────────────────────
        self._extract_label_based(cleaned, fields, confidences)

        if "full_name" not in fields:
            self._extract_name_between_anchors(cleaned, fields, confidences)

        # 3. Fuzzy fallback for nationality ──────────────────────────────
        if "nationality" not in fields:
            self._extract_nationality_fuzzy(cleaned, fields, confidences)

        # 4. Defaults for any field still missing ────────────────────────
        result = self._fill_defaults(fields, confidences)

        logger.debug(
            "RealFieldExtractor.extract done | confidences={}",
            {k: round(v, 2) for k, v in result.confidences.items()},
        )
        return result

    # ── extraction helpers ───────────────────────────────────────────────

    def _extract_id_number(
        self, lines: list[TextLine], fields: dict[str, str], confidences: dict[str, float]
    ) -> None:
        candidates = [
            (match.group(1), _line_confidence(rule, line))
            for rule, transform in ((1.0, str), (0.9, lambda t: _ID_SEPARATORS_RE.sub("", t)))
            for line in lines
            for match in _ID12_RE.finditer(transform(line.text))
        ]
        valid = next((c for c in candidates if decode_cccd_number(c[0]) is not None), None)
        if valid is None:
            # Trang photo ghi "CMND 9 số, CCCD 12 số" cùng dòng và OCR bỏ mất dấu phẩy: thử 12 số đầu/cuối
            # của chuỗi số dài, chỉ nhận khi đúng 1 cách tách hợp lệ (đoán ranh giới nên luôn cần rà soát).
            glued = [
                (piece, _line_confidence(_SUSPECT_CONFIDENCE, line))
                for line in lines
                for run in _LONG_DIGITS_RE.findall(_ID_SEPARATORS_RE.sub("", line.text))
                for piece in {run[:12], run[-12:]}
                if decode_cccd_number(piece) is not None
            ]
            if len({piece for piece, _ in glued}) == 1:
                valid = glued[0]
        if valid is not None:
            fields["id_number"], confidences["id_number"] = valid
        elif candidates:
            fields["id_number"] = candidates[0][0]
            confidences["id_number"] = min(candidates[0][1], _SUSPECT_CONFIDENCE)

    def _extract_dates(
        self,
        lines: list[TextLine],
        fields: dict[str, str],
        confidences: dict[str, float],
        id_info: CCCDNumberInfo | None = None,
    ) -> None:
        """Ngày sinh = ngày sớm nhất (ưu tiên ngày khớp năm sinh trong số CCCD); muộn nhất = hạn."""
        valid_dates: list[tuple[datetime, str, TextLine]] = []
        for line in lines:
            for m in _DATE_RE.finditer(line.text):
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                normalized = f"{d:02d}/{mo:02d}/{y:04d}"
                try:
                    parsed = datetime.strptime(normalized, "%d/%m/%Y")
                except ValueError:
                    continue  # invalid calendar date
                valid_dates.append((parsed, normalized, line))

        if not valid_dates:
            return
        # Sắp theo thời gian thay vì thứ tự dòng: thứ tự bbox có thể lệch khi ảnh nghiêng.
        valid_dates.sort(key=lambda item: item[0])
        earliest, latest = valid_dates[0], valid_dates[-1]
        dob = earliest
        if id_info is not None:
            dob = next((d for d in valid_dates if d[0].year == id_info.birth_year), earliest)
        fields["dob"] = dob[1]
        confidences["dob"] = _line_confidence(0.95, dob[2])
        # Bỏ qua ngày sớm nhất chỉ dựa vào số CCCD (có thể chính số đó bị đọc sai) -> cần user xác nhận.
        if dob is not earliest:
            confidences["dob"] = min(confidences["dob"], _SUSPECT_CONFIDENCE)
        later = [d for d in valid_dates if d[0] > dob[0]]
        if not later:
            return
        expiry = later[-1]
        fields["expiry_date"] = expiry[1]
        confidences["expiry_date"] = _line_confidence(0.95, expiry[2])
        born, ends = dob[0], expiry[0]
        # Năm hết hạn đúng mốc tuổi mà ngày/tháng khác sinh nhật: một trong hai ngày bị đọc sai chữ số.
        # Ảnh thật có QR: 3/3 ngày sinh sai đều lệch kiểu này (1 ca đang không bị cảnh báo).
        if (
            ends.year - born.year in _EXPIRY_AGES
            and (ends.day, ends.month) != (born.day, born.month)
            and (born.day, born.month) != (29, 2)
        ):
            for name in ("dob", "expiry_date"):
                confidences[name] = min(confidences[name], _SUSPECT_CONFIDENCE)

    @staticmethod
    def _cross_check_id(
        fields: dict[str, str], confidences: dict[str, float], id_info: CCCDNumberInfo | None
    ) -> None:
        if id_info is None:
            return
        # Giới tính được mã hóa trong số CCCD: suy ra từ số chắc như chính số đó, và khi chữ "Nam/Nữ"
        # đọc được trùng khớp thì hai nguồn độc lập xác nhận nhau -> lấy độ tin cậy cao hơn.
        if "gender" not in fields:
            fields["gender"] = id_info.gender
            confidences["gender"] = confidences["id_number"]
        elif fields["gender"] == id_info.gender:
            confidences["gender"] = max(confidences["gender"], confidences["id_number"])
        conflicts = [
            name
            for name, ok in (
                ("gender", fields["gender"] == id_info.gender),
                ("dob", "dob" not in fields or int(fields["dob"][-4:]) == id_info.birth_year),
            )
            if not ok
        ]
        if conflicts:
            for name in ("id_number", *conflicts):
                confidences[name] = min(confidences[name], _SUSPECT_CONFIDENCE)

    def _extract_gender(
        self,
        lines: list[TextLine],
        fields: dict[str, str],
        confidences: dict[str, float],
    ) -> None:
        """Tìm "Nam"/"Nữ" – ưu tiên dòng standalone, sau đó token trong dòng."""
        # Pass 1: dòng chỉ chứa "Nam" hoặc "Nữ"
        for line in lines:
            t = line.text.strip()
            if t == "Nam" or t == "Nữ":
                fields["gender"] = t
                confidences["gender"] = _line_confidence(0.95, line)
                return

        # Pass 2: dòng có label "Giới tính:" / "Sex:" + value
        for line in lines:
            norm = _normalize(line.text)
            if _LABEL_PATTERNS["gender"].search(norm):
                # Lấy phần sau ":"
                after_colon = _VALUE_AFTER_COLON.search(line.text)
                tail = after_colon.group(1) if after_colon else line.text
                if "Nữ" in tail or re.search(r"\bN[uũ]\b", tail):
                    fields["gender"] = "Nữ"
                    confidences["gender"] = _line_confidence(0.85, line)
                    return
                if _GENDER_NAM_RE.search(tail):
                    fields["gender"] = "Nam"
                    confidences["gender"] = _line_confidence(0.85, line)
                    return

        # Pass 3: token "Nam" / "Nữ" trong dòng ngắn
        for line in lines:
            if len(line.text.strip()) > _GENDER_FALLBACK_MAX_LEN:
                continue
            if "Nữ" in line.text:
                fields["gender"] = "Nữ"
                confidences["gender"] = _line_confidence(0.7, line)
                return
            if _GENDER_NAM_RE.search(line.text):
                fields["gender"] = "Nam"
                confidences["gender"] = _line_confidence(0.7, line)
                return

    def _extract_label_based(
        self,
        lines: list[TextLine],
        fields: dict[str, str],
        confidences: dict[str, float],
    ) -> None:
        """Quét label patterns; value = sau ":" hoặc dòng kế tiếp non-label.

        Chỉ điền nếu field chưa có (regex/global đã tốt hơn).
        """
        # Pre-normalize text mỗi line 1 lần (để regex match ascii).
        normalized = [_normalize(line.text) for line in lines]

        # Build label index: line_idx → set of fields it labels
        line_label_fields: dict[int, set[str]] = {}
        for idx, norm_text in enumerate(normalized):
            for field, pattern in _LABEL_PATTERNS.items():
                if pattern.search(norm_text):
                    line_label_fields.setdefault(idx, set()).add(field)

        # For each field, find first label match + extract value
        target_fields = ("full_name", "origin", "residence")
        for field in target_fields:
            if field in fields:
                continue
            found = self._value_for_field(field, lines, normalized, line_label_fields)
            if found:
                value, sources = found
                missing_province = False
                unverified = value
                if field in ("origin", "residence"):
                    value, sources = self._extend_to_province(value, sources, lines, line_label_fields)
                    address = match_address(value)
                    value, missing_province, unverified = address.text, not address.has_province, address.unverified
                fields[field] = value
                confidences[field] = _line_confidence(0.85, *sources)
                last = next(i for i, line in enumerate(lines) if line is sources[-1])
                weakest = _weakest_char(unverified, sources)
                # Địa chỉ trên CCCD luôn kết thúc bằng tỉnh: thiếu tỉnh nghĩa là bị cắt dòng hoặc đọc sai.
                if (
                    _implausible_text(field, value)
                    or missing_province
                    or (weakest is not None and weakest < _WEAK_CHAR_CONFIDENCE)
                    or (field == "residence" and self._continues_address(last + 1, lines, normalized, line_label_fields))
                ):
                    confidences[field] = min(confidences[field], _SUSPECT_CONFIDENCE)

    def _extend_to_province(
        self,
        value: str,
        sources: list[TextLine],
        lines: list[TextLine],
        line_label_fields: dict[int, set[str]],
    ) -> tuple[str, list[TextLine]]:
        """Địa chỉ chưa tới tên tỉnh: ghép tối đa 2 dòng kế (không phải nhãn/ngày) nếu dòng cuối kết thúc bằng tỉnh.

        Dòng cuối địa chỉ thường chỉ có "Hưng Hà, Thái Bình" (không chữ Xã/Huyện) nên luật đơn vị hành chính bỏ sót.
        """
        if ends_with_province(value):
            return value, sources
        start = next(i for i, line in enumerate(lines) if line is sources[0]) + 1
        following = [i for i in range(start, len(lines)) if not any(lines[i] is src for src in sources)]
        extra: list[TextLine] = []
        for idx in following[:2]:
            text = self._strip_punct(lines[idx].text)
            if idx in line_label_fields or _DATE_RE.search(text) or len(text) < 3:
                break
            extra.append(lines[idx])
            if ends_with_province(text):
                merged = ", ".join([value, *(self._strip_punct(line.text) for line in extra)])
                return merged, [*sources, *extra]
        return value, sources

    @staticmethod
    def _extract_name_between_anchors(
        lines: list[TextLine], fields: dict[str, str], confidences: dict[str, float]
    ) -> None:
        """Mất nhãn "Họ và tên": trên mặt trước tên là dòng in hoa nằm giữa dòng số CCCD và dòng ngày sinh.

        Chỉ đoán theo vị trí nên luôn để confidence nghi ngờ cho user xác nhận.
        """
        if "id_number" not in fields or "dob" not in fields:
            return
        id_idx = next(
            (i for i, line in enumerate(lines) if fields["id_number"] in _ID_SEPARATORS_RE.sub("", line.text)), None
        )
        dob_idx = next((i for i, line in enumerate(lines) if _normalized_dates(line.text) & {fields["dob"]}), None)
        if id_idx is None or dob_idx is None or dob_idx <= id_idx + 1:
            return
        def is_upper_text(line: TextLine) -> bool:
            value = RealFieldExtractor._strip_punct(line.text)
            letters = [c for c in value if c.isalpha()]
            return (
                bool(letters)
                and sum(c.isupper() for c in letters) / len(letters) >= _NAME_UPPER_RATIO
                and not re.search(r"\d", value)
                and not any(p.search(_normalize(value)) for p in _LABEL_PATTERNS.values())
            )

        between = lines[id_idx + 1 : dob_idx]
        for line in between:
            value = RealFieldExtractor._strip_punct(line.text)
            if is_upper_text(line) and not _implausible_text("full_name", value):
                fields["full_name"] = value
                confidences["full_name"] = min(_line_confidence(0.85, line), _SUSPECT_CONFIDENCE)
                return

        # Detector đôi khi tách họ tên thành từng chữ một box: ghép các dòng in hoa liền nhau.
        run: list[TextLine] = []
        for line in [*between, None]:
            if line is not None and is_upper_text(line):
                run.append(line)
                continue
            if len(run) > 1:
                value = " ".join(RealFieldExtractor._strip_punct(part.text) for part in run)
                if not _implausible_text("full_name", value):
                    fields["full_name"] = value
                    confidences["full_name"] = min(_line_confidence(0.85, *run), _SUSPECT_CONFIDENCE)
                    return
            run = []

    @staticmethod
    def _continues_address(
        idx: int, lines: list[TextLine], normalized: list[str], line_label_fields: dict[int, set[str]]
    ) -> bool:
        """Dòng ngay sau phần đã lấy vẫn giống địa chỉ -> nơi thường trú có thể bị cắt (chỉ gộp tối đa 2 dòng)."""
        return (
            idx < len(lines)
            and idx not in line_label_fields
            and len(lines[idx].text.strip()) >= 5
            and not _DATE_RE.search(lines[idx].text)
            and bool(_ADMIN_UNIT_RE.search(normalized[idx]))
        )

    def _value_for_field(
        self,
        field: str,
        lines: list[TextLine],
        normalized: list[str],
        line_label_fields: dict[int, set[str]],
    ) -> tuple[str, list[TextLine]] | None:
        """Tìm value của 1 field theo label-based; trả kèm các dòng nguồn để tính độ tin cậy."""
        for idx, line in enumerate(lines):
            if field not in line_label_fields.get(idx, set()):
                continue

            # Strategy 1a: value sau ":" trên cùng dòng
            after = _VALUE_AFTER_COLON.search(line.text)
            if after:
                candidate = after.group(1)
                if field in ("origin", "residence"):
                    candidate = _drop_place_label(candidate)
                candidate = self._strip_punct(candidate)
                # Loại noise: candidate có thể là phần English label
                # ("Full name") nếu line là "Họ và tên / Full name:" → skip.
                if candidate and not self._is_label_only(candidate):
                    # Đo trên ảnh thật: dòng kế không có đơn vị hành chính thường là nhãn khác đọc sai.
                    return self._with_next_line(
                        field, idx, candidate, lines, normalized, line_label_fields, need_admin_unit=True
                    )

            # Strategy 1b: value sau ALL label patterns (no colon)
            # Vd OCR: "Nơi thường trúi Place of residene Tổ 13, Khu Phố 6"
            # → cắt sau "residence" → "Tổ 13, Khu Phố 6"
            after_label = self._value_after_all_labels(line.text, normalized[idx])
            if after_label and field in ("origin", "residence"):
                after_label = self._strip_punct(_drop_place_label(after_label)) or None
            if after_label:
                return self._with_next_line(field, idx, after_label, lines, normalized, line_label_fields)

            # Strategy 2: dòng kế tiếp không phải label
            for next_idx in range(idx + 1, min(idx + 4, len(lines))):
                if next_idx in line_label_fields:
                    break  # gặp label khác → stop
                candidate = lines[next_idx].text.strip()
                candidate = self._strip_label_prefix(candidate, normalized[next_idx])
                if candidate and not self._is_label_only(candidate):
                    # Cho residence + origin: gộp 2 dòng nếu dòng kế dài (multi-line)
                    if field in ("origin", "residence"):
                        merged = candidate
                        sources = [lines[next_idx]]
                        nxt2 = next_idx + 1
                        if (
                            nxt2 < len(lines)
                            and nxt2 not in line_label_fields
                            and len(lines[nxt2].text.strip()) >= 5
                            and not _DATE_RE.search(lines[nxt2].text)
                        ):
                            extra = lines[nxt2].text.strip()
                            extra = self._strip_label_prefix(extra, normalized[nxt2])
                            if extra and not self._is_label_only(extra):
                                merged = f"{merged}, {extra}"
                                sources.append(lines[nxt2])
                        return self._strip_punct(merged), sources
                    return self._strip_punct(candidate), [lines[next_idx]]
        return None

    def _with_next_line(
        self,
        field: str,
        idx: int,
        value: str,
        lines: list[TextLine],
        normalized: list[str],
        line_label_fields: dict[int, set[str]],
        *,
        need_admin_unit: bool = False,
    ) -> tuple[str, list[TextLine]]:
        """Giá trị nằm trên dòng nhãn; quê quán/thường trú ghép thêm dòng kế nếu không phải nhãn/ngày."""
        sources = [lines[idx]]
        nxt = idx + 1
        # Detector hay cắt dòng nhãn thành 2 box chồng nhau ("...residence: 1" + "12/34 Lê Lợi") và
        # thứ tự đọc có thể đặt box bên phải sau dòng dưới: box cùng hàng là phần còn lại của giá trị.
        same_row = [
            j for j, line in enumerate(lines)
            if j != idx and j not in line_label_fields and _same_row_right(lines[idx].bbox, line.bbox)
        ]
        if field in ("origin", "residence") and same_row:
            cont = min(same_row, key=lambda j: lines[j].bbox.xmin)
            rest = self._strip_punct(lines[cont].text.strip())
            value = rest if rest.startswith(value) else f"{value} {rest}"
            sources.append(lines[cont])
            need_admin_unit = False
            if nxt == cont:
                nxt += 1
        if (
            field in ("origin", "residence")
            and nxt < len(lines)
            and nxt not in line_label_fields
            and len(lines[nxt].text.strip()) >= 5
            and not _DATE_RE.search(lines[nxt].text)
            and (not need_admin_unit or _ADMIN_UNIT_RE.search(normalized[nxt]))
        ):
            extra = self._strip_label_prefix(lines[nxt].text.strip(), normalized[nxt])
            if extra and not self._is_label_only(extra):
                return self._strip_punct(f"{value}, {extra}"), [*sources, lines[nxt]]
        return self._strip_punct(value), sources

    @staticmethod
    def _value_after_all_labels(original: str, norm_text: str) -> str | None:
        """Cắt phần sau LAST label match (qua tất cả patterns).

        Lưu ý: `_normalize` preserve character count → position trong norm
        bằng position trong original. Hợp lý cho substring slicing.
        """
        last_end = 0
        for pattern in _LABEL_PATTERNS.values():
            for m in pattern.finditer(norm_text):
                last_end = max(last_end, _label_end(pattern, norm_text, m.start()))
        if last_end == 0:
            return None
        suffix = RealFieldExtractor._strip_punct(original[last_end:])
        if not any(c.isalnum() for c in suffix):
            return None
        # Kiểm tra suffix có vẻ là label-only (vd "Place of residence" nếu
        # chỉ matched Vietnamese label trước đó).
        if RealFieldExtractor._is_label_only(suffix):
            return None
        return suffix

    @staticmethod
    def _strip_label_prefix(text: str, norm_text: str) -> str:
        """Bỏ phần label đầu dòng nếu có (vd 'Quê quán: Hà Nội' → 'Hà Nội')."""
        for pattern in _LABEL_PATTERNS.values():
            m = pattern.search(norm_text)
            if m and m.start() <= 2:
                # Cắt sau ":" nếu có (in original text)
                colon_match = _VALUE_AFTER_COLON.search(text)
                if colon_match:
                    return colon_match.group(1).strip()
                # Không có ":" → cắt phần text gốc tương ứng (ascii ko thay đổi length)
                return text[_label_end(pattern, norm_text):].lstrip(": .,;").strip()
        return text

    @staticmethod
    def _is_label_only(text: str) -> bool:
        """True nếu line chỉ chứa label (không có value)."""
        stripped = text.strip(" :./").strip()
        if not stripped:
            return True
        norm = _normalize(stripped)
        for pattern in _LABEL_PATTERNS.values():
            if pattern.fullmatch(norm):
                return True
        return False

    @staticmethod
    def _strip_punct(text: str) -> str:
        """Trim các ký tự nhiễu thường gặp ở đầu/cuối value."""
        return text.strip(" :./,;-").strip()

    def _extract_nationality_fuzzy(
        self,
        lines: list[TextLine],
        fields: dict[str, str],
        confidences: dict[str, float],
    ) -> None:
        """Fuzzy match 'Việt Nam' để handle OCR errors phổ biến."""
        try:
            from rapidfuzz import fuzz  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("rapidfuzz chưa cài; bỏ qua fuzzy nationality.")
            return

        target = "Việt Nam"
        best_score = 0.0
        best_line: TextLine | None = None
        for line in lines:
            # partial_ratio match substring tốt với label-prefixed lines
            score = fuzz.partial_ratio(target.lower(), line.text.lower())
            if score > best_score:
                best_score, best_line = score, line
        if best_line is not None and best_score >= self.fuzzy_threshold:
            fields["nationality"] = target
            rule = 0.85 if best_score >= 90 else 0.7
            confidences["nationality"] = _line_confidence(rule, best_line)

    # ── defaults ─────────────────────────────────────────────────────────

    def _fill_defaults(
        self, fields: dict[str, str], confidences: dict[str, float]
    ) -> ExtractionResult:
        """Điền placeholder cho fields còn thiếu để pass schema validation."""
        for key, default in self._DEFAULTS.items():
            if key not in fields or not fields[key]:
                fields[key] = default
                confidences[key] = 0.0
        # expiry_date là Optional ở schema; không điền default ở đây.
        return ExtractionResult(fields=fields, confidences=confidences)


__all__ = ["MockExtractor", "RealFieldExtractor"]
