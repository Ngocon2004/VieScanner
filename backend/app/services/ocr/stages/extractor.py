"""Extractor – stage ⑤ của pipeline.

- `MockExtractor`: giả định detector + recognizer cấp đúng 8 dòng theo thứ tự
  chuẩn của CCCD, map 1-1 sang field name.
- `RealFieldExtractor`: rule-based extraction từ list `TextLine` → CCCDData.

Chiến lược 3 tầng (theo độ tin cậy giảm dần):

1. **Global regex** (confidence cao 0.95-1.0):
   - `id_number`: `\d{12}` đầu tiên trong toàn bộ text.
   - `dob` / `expiry_date`: `dd/mm/yyyy` có lịch hợp lệ. Date đầu = DOB, kế = expiry.
   - `gender`: standalone "Nam" hoặc "Nữ" (token chính xác).

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
from datetime import datetime
from typing import Any

from app.core.logging import logger
from app.services.ocr.interfaces import ExtractionResult, TextLine


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
            confidences[name] = line.recognizer_confidence
        logger.debug("MockExtractor.extract | fields={}", list(fields.keys()))
        return ExtractionResult(fields=fields, confidences=confidences)


# ─────────────────────────────────────────────────────────────────────────────
# Real – rule-based extractor
# ─────────────────────────────────────────────────────────────────────────────


# Regex cho global extraction.
_ID12_RE = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_DATE_RE = re.compile(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})")

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
    # Vietnamese: "thuong tru" hoặc "thuong trui" (OCR thêm i).
    "residence": re.compile(
        r"thuong\s*trui?|noi\s*thuong|place\s*of\s*residenc?e?",
        re.IGNORECASE,
    ),
    # "Có giá trị đến / Date of expiry"
    "expiry_date": re.compile(
        r"co\s*gia\s*tri|date\s*of\s*expiry|han\s*su\s*dung",
        re.IGNORECASE,
    ),
}

# Sau khi match label, value thường nằm sau ":" hoặc "/<English>:".
_VALUE_AFTER_COLON = re.compile(r":\s*(.+)$")


class RealFieldExtractor:
    """Rule-based extractor cho CCCD layout 2016/2020."""

    # Default placeholders – pass schema validation, confidence=0.
    # Form FE sẽ highlight (Phase 3) cho user nhận biết.
    _DEFAULTS: dict[str, str] = {
        "id_number": "000000000000",
        "full_name": "(không nhận dạng được)",
        "dob": "01/01/2000",
        "gender": "Nam",
        "nationality": "Việt Nam",
        "origin": "(không nhận dạng được)",
        "residence": "(không nhận dạng được)",
    }

    # Khi confidence dưới threshold này, dù có value vẫn coi là không tin cậy.
    _MIN_CONFIDENCE = 0.0

    def __init__(self, *, fuzzy_threshold: int = 80) -> None:
        self.fuzzy_threshold = fuzzy_threshold

    def extract(self, lines: list[TextLine]) -> ExtractionResult:
        cleaned = [line for line in lines if line.text and line.text.strip()]
        if not cleaned:
            logger.warning("RealFieldExtractor: 0 input lines.")
            return self._fill_defaults({}, {})

        fields: dict[str, str] = {}
        confidences: dict[str, float] = {}

        # Pre-compute concatenated text & line texts for global queries.
        all_texts = [line.text.strip() for line in cleaned]
        all_text = " | ".join(all_texts)

        # 1. Global regex extractions ────────────────────────────────────
        self._extract_id_number(all_text, fields, confidences)
        self._extract_dates(cleaned, fields, confidences)
        self._extract_gender(cleaned, fields, confidences)

        # 2. Label-based extractions ─────────────────────────────────────
        self._extract_label_based(cleaned, fields, confidences)

        # 3. Fuzzy fallback for nationality ──────────────────────────────
        if "nationality" not in fields:
            self._extract_nationality_fuzzy(all_texts, fields, confidences)

        # 4. Defaults for any field still missing ────────────────────────
        result = self._fill_defaults(fields, confidences)

        logger.debug(
            "RealFieldExtractor.extract done | fields={} | confidences={}",
            {k: (v if k != "full_name" else v[:30]) for k, v in result.fields.items()},
            {k: round(v, 2) for k, v in result.confidences.items()},
        )
        return result

    # ── extraction helpers ───────────────────────────────────────────────

    def _extract_id_number(
        self, all_text: str, fields: dict[str, str], confidences: dict[str, float]
    ) -> None:
        match = _ID12_RE.search(all_text)
        if match:
            fields["id_number"] = match.group(1)
            confidences["id_number"] = 1.0

    def _extract_dates(
        self,
        lines: list[TextLine],
        fields: dict[str, str],
        confidences: dict[str, float],
    ) -> None:
        """Tìm tất cả date hợp lệ trong các dòng. First = DOB, second = expiry."""
        valid_dates: list[tuple[str, TextLine]] = []
        for line in lines:
            for m in _DATE_RE.finditer(line.text):
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                normalized = f"{d:02d}/{mo:02d}/{y:04d}"
                try:
                    datetime.strptime(normalized, "%d/%m/%Y")
                except ValueError:
                    continue  # invalid calendar date
                valid_dates.append((normalized, line))

        # Heuristic: first valid date = DOB, second (if khác và sau DOB về y) = expiry.
        if valid_dates:
            fields["dob"] = valid_dates[0][0]
            confidences["dob"] = 0.95
        if len(valid_dates) >= 2:
            # Nếu 2 date cùng giá trị → có thể OCR lặp; bỏ qua expiry.
            if valid_dates[1][0] != valid_dates[0][0]:
                fields["expiry_date"] = valid_dates[1][0]
                confidences["expiry_date"] = 0.95

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
                confidences["gender"] = 0.95
                return

        # Pass 2: dòng có label "Giới tính:" / "Sex:" + value
        for line in lines:
            norm = _normalize(line.text)
            if _LABEL_PATTERNS["gender"].search(norm):
                # Lấy phần sau ":"
                after_colon = _VALUE_AFTER_COLON.search(line.text)
                tail = after_colon.group(1) if after_colon else line.text
                if re.search(r"\bNam\b", tail):
                    fields["gender"] = "Nam"
                    confidences["gender"] = 0.85
                    return
                if "Nữ" in tail or re.search(r"\bN[uũ]\b", tail):
                    fields["gender"] = "Nữ"
                    confidences["gender"] = 0.85
                    return

        # Pass 3: token "Nam" / "Nữ" trong bất kỳ dòng nào
        for line in lines:
            if re.search(r"\bNam\b", line.text):
                fields["gender"] = "Nam"
                confidences["gender"] = 0.7
                return
            if "Nữ" in line.text:
                fields["gender"] = "Nữ"
                confidences["gender"] = 0.7
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
            value = self._value_for_field(field, lines, normalized, line_label_fields)
            if value:
                fields[field] = value
                confidences[field] = 0.85

    def _value_for_field(
        self,
        field: str,
        lines: list[TextLine],
        normalized: list[str],
        line_label_fields: dict[int, set[str]],
    ) -> str | None:
        """Tìm value của 1 field theo label-based."""
        for idx, line in enumerate(lines):
            if field not in line_label_fields.get(idx, set()):
                continue

            # Strategy 1a: value sau ":" trên cùng dòng
            after = _VALUE_AFTER_COLON.search(line.text)
            if after:
                candidate = after.group(1).strip()
                # Loại noise: candidate có thể là phần English label
                # ("Full name") nếu line là "Họ và tên / Full name:" → skip.
                if candidate and not self._is_label_only(candidate):
                    return self._strip_punct(candidate)

            # Strategy 1b: value sau ALL label patterns (no colon)
            # Vd OCR: "Nơi thường trúi Place of residene Tổ 13, Khu Phố 6"
            # → cắt sau "residence" → "Tổ 13, Khu Phố 6"
            after_label = self._value_after_all_labels(line.text, normalized[idx])
            if after_label:
                # Cho origin/residence: thử merge với dòng kế tiếp non-label
                if field in ("origin", "residence"):
                    nxt = idx + 1
                    if (
                        nxt < len(lines)
                        and nxt not in line_label_fields
                        and len(lines[nxt].text.strip()) >= 5
                        and not _DATE_RE.search(lines[nxt].text)
                    ):
                        extra = self._strip_label_prefix(
                            lines[nxt].text.strip(), normalized[nxt]
                        )
                        if extra and not self._is_label_only(extra):
                            return self._strip_punct(f"{after_label}, {extra}")
                return self._strip_punct(after_label)

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
                        return self._strip_punct(merged)
                    return self._strip_punct(candidate)
        return None

    @staticmethod
    def _value_after_all_labels(original: str, norm_text: str) -> str | None:
        """Cắt phần sau LAST label match (qua tất cả patterns).

        Lưu ý: `_normalize` preserve character count → position trong norm
        bằng position trong original. Hợp lý cho substring slicing.
        """
        last_end = 0
        for pattern in _LABEL_PATTERNS.values():
            for m in pattern.finditer(norm_text):
                last_end = max(last_end, m.end())
        if last_end == 0:
            return None
        suffix = original[last_end:].lstrip(": ./,").strip()
        if not suffix:
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
                return text[m.end():].lstrip(": .,").strip()
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
        all_texts: list[str],
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
        for text in all_texts:
            # partial_ratio match substring tốt với label-prefixed lines
            score = fuzz.partial_ratio(target.lower(), text.lower())
            best_score = max(best_score, score)
        if best_score >= self.fuzzy_threshold:
            fields["nationality"] = target
            confidences["nationality"] = 0.85 if best_score >= 90 else 0.7

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
