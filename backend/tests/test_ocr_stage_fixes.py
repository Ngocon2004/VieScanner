from __future__ import annotations

import unicodedata
from datetime import date
from typing import Any

import pytest

from app.core.config import settings
from app.core.exceptions import OCRFailedError
from app.services.ocr.cccd_number import decode_cccd_number
from app.services.ocr.interfaces import BBox, ExtractionResult, OCRStageError, TextLine
from app.services.ocr.pipeline import OCRPipeline
from app.services.ocr.placeholders import FIELD_PLACEHOLDERS
from app.services.ocr.stages import (
    MockAligner,
    MockCleaner,
    MockDetector,
    MockRecognizer,
    RealFieldExtractor,
    RealImageCleaner,
)
from app.services.ocr.stages.aligner import RealCardAligner
from app.services.ocr.stages.detector import _reading_order
from app.utils.privacy import mask_id_number

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")


def _lines(*texts: str, prob: float | None = 0.99) -> list[TextLine]:
    return [
        TextLine(text=t, bbox=BBox(0, i * 20, 300, i * 20 + 18), recognizer_confidence=prob)
        for i, t in enumerate(texts)
    ]


def _png(h: int = 96, w: int = 160) -> bytes:
    ok, buf = cv2.imencode(".png", np.zeros((h, w, 3), dtype=np.uint8))
    assert ok
    return buf.tobytes()


class FixedExtractor:
    def __init__(self, **overrides: str) -> None:
        self.overrides = overrides

    def extract(self, lines: list[TextLine]) -> ExtractionResult:
        fields = {
            "id_number": "001202000123",
            "full_name": "NGUYEN VAN A",
            "dob": "01/01/2002",
            "gender": "Nam",
            "nationality": "Việt Nam",
            "origin": "Hà Nội",
            "residence": "Hà Nội",
            "expiry_date": "01/01/2030",
            **self.overrides,
        }
        return ExtractionResult(fields=fields, confidences={k: 0.9 for k in fields})


def _pipeline(extractor: Any = None, aligner: Any = None) -> OCRPipeline:
    return OCRPipeline(
        aligner=aligner or MockAligner(),
        cleaner=MockCleaner(),
        detector=MockDetector(),
        recognizer=MockRecognizer(),
        extractor=extractor or FixedExtractor(),
    )


# ---------------------------------------------------------------- extractor


def test_gender_is_not_read_from_nationality_or_long_address() -> None:
    result = RealFieldExtractor().extract(
        _lines(
            "Quốc tịch / Nationality: Việt Nam",
            "Nơi thường trú: Thôn 2, Xã Tam Kỳ, Tỉnh Quảng Nam",
        )
    )
    assert result.confidences["gender"] == 0.0


def test_gender_reads_female_from_label_line() -> None:
    result = RealFieldExtractor().extract(_lines("Giới tính / Sex: Nữ   Quốc tịch: Việt Nam"))
    assert result.fields["gender"] == "Nữ"


def test_dates_are_ordered_chronologically_not_by_line() -> None:
    result = RealFieldExtractor().extract(
        _lines("Có giá trị đến: 15/03/2041", "Ngày sinh / Date of birth: 15/03/2001")
    )
    assert result.fields["dob"] == "15/03/2001"
    assert result.fields["expiry_date"] == "15/03/2041"


def test_id_number_with_spaces_is_recognized() -> None:
    result = RealFieldExtractor().extract(_lines("Số / No.: 001 202 000 123"))
    assert result.fields["id_number"] == "001202000123"
    assert 0 < result.confidences["id_number"] < 1.0


def test_decomposed_unicode_does_not_shift_label_slicing() -> None:
    nfd = unicodedata.normalize("NFD", "Quê quán Place of origin Phường Bến Nghé")
    result = RealFieldExtractor().extract(_lines(nfd))
    assert result.fields["origin"] == "Phường Bến Nghé"


def test_field_confidence_is_capped_by_recognizer_probability() -> None:
    low = RealFieldExtractor().extract(_lines("Số / No.: 001202000123", prob=0.4))
    unknown = RealFieldExtractor().extract(_lines("Số / No.: 001202000123", prob=None))
    assert low.confidences["id_number"] == pytest.approx(0.4)
    assert unknown.confidences["id_number"] == pytest.approx(1.0)


def test_semicolon_misread_after_label_still_takes_name_on_next_line() -> None:
    result = RealFieldExtractor().extract(_lines("Họ và tên / Full name;", "NGUYỄN VĂN AN"))
    assert result.fields["full_name"] == "NGUYỄN VĂN AN"
    assert result.confidences["full_name"] > 0.6


def test_name_between_id_and_dob_when_label_unreadable() -> None:
    result = RealFieldExtractor().extract(
        _lines("Số / No.: 001202000123", "Hò vi tèn / Fll nme", "NGUYỄN VĂN AN", "Ngày sinh / Date of birth: 01/01/2002")
    )
    assert result.fields["full_name"] == "NGUYỄN VĂN AN"
    assert 0 < result.confidences["full_name"] < 0.6


@pytest.mark.parametrize("label", ["Nơi cư trú / Place of residence:", "Nơi cut trú/P.", "Nơi cư ttrú:"])
def test_residence_label_of_2024_card_back_is_recognized(label: str) -> None:
    result = RealFieldExtractor().extract(
        _lines(f"{label} Phường Ba Đình, Hà Nội", "Nơi đăng ký khai sinh / Place of birth: Hà Nội")
    )
    assert result.fields["residence"].endswith("Hà Nội")
    assert "khai sinh" not in result.fields["residence"]


def test_name_split_into_one_word_boxes_is_joined() -> None:
    result = RealFieldExtractor().extract(
        _lines("Số / No.: 001202000123", "NGUYỄN", "VĂN", "AN", "Ngày sinh / Date of birth: 01/01/2002")
    )
    assert result.fields["full_name"] == "NGUYỄN VĂN AN"
    assert 0 < result.confidences["full_name"] < 0.6


def test_name_anchor_fallback_skips_non_uppercase_lines() -> None:
    result = RealFieldExtractor().extract(
        _lines("Số / No.: 001202000123", "Hò vi tèn / Fll nme", "Ngày sinh / Date of birth: 01/01/2002")
    )
    assert result.confidences["full_name"] == 0.0


# ----------------------------------------------------------------- trường chữ bất thường


def test_plausible_text_fields_keep_high_confidence() -> None:
    result = RealFieldExtractor().extract(
        _lines(
            "Họ và tên / Full name:",
            "NGUYỄN VĂN AN",
            "Quê quán / Place of origin: Hưng Hà, Thái Bình",
            "Nơi thường trú / Place of residence: Thôn 2, Xã Tam Kỳ",
            "Huyện Núi Thành, Tỉnh Quảng Nam",
        )
    )
    assert result.fields["full_name"] == "NGUYỄN VĂN AN"
    assert result.fields["residence"] == "Thôn 2, Xã Tam Kỳ, Huyện Núi Thành, Tỉnh Quảng Nam"
    for name in ("full_name", "origin", "residence"):
        assert result.confidences[name] > 0.6


@pytest.mark.parametrize(
    "name_line",
    ["NGUYỄN VĂN 4N", "NGUYỄN VĂN AN Full", "AN", "NGUYỄN# VĂN AN"],
)
def test_implausible_name_is_flagged(name_line: str) -> None:
    result = RealFieldExtractor().extract(_lines("Họ và tên:", name_line))
    assert result.confidences["full_name"] <= 0.5


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ("Quê quán: Bình", "origin"),
        ("Quê quán: Thôn 12 Hưng Hà", "origin"),
        ("Nơi thường trú: Hưng Hà Thái Bình", "residence"),
    ],
)
def test_implausible_place_is_flagged(line: str, field: str) -> None:
    assert RealFieldExtractor().extract(_lines(line)).confidences[field] <= 0.5


def test_value_after_colon_does_not_absorb_non_address_line() -> None:
    result = RealFieldExtractor().extract(
        _lines("Nơi thường trú: Thôn 2, Xã Tam Kỳ, Huyện Núi Thành", "Nốt ruồi C:2cm trên mép")
    )
    assert result.fields["residence"] == "Thôn 2, Xã Tam Kỳ, Huyện Núi Thành"


def test_place_name_containing_label_like_syllables_is_not_flagged() -> None:
    result = RealFieldExtractor().extract(
        _lines("Nơi thường trú: Phố Thọ Tến, Xã Hồ Tùng Mậu, Huyện Ân Thi, Tỉnh Hưng Yên")
    )
    assert result.confidences["residence"] > 0.6


def test_three_line_residence_is_merged_up_to_province() -> None:
    result = RealFieldExtractor().extract(
        _lines(
            "Nơi thường trú: Số 12, Tổ 3",
            "Khu phố 6, Phường Bến Nghé",
            "Quận 1, Thành phố Hồ Chí Minh",
        )
    )
    assert result.fields["residence"] == "Số 12, Tổ 3, Khu phố 6, Phường Bến Nghé, Quận 1, Thành phố Hồ Chí Minh"
    assert result.confidences["residence"] > 0.6


def test_residence_without_province_is_flagged() -> None:
    result = RealFieldExtractor().extract(_lines("Nơi thường trú: Số 12, Tổ 3, Khu phố 6, Phường Bến Nghé"))
    assert result.confidences["residence"] <= 0.5


def test_last_address_line_without_admin_word_is_merged() -> None:
    result = RealFieldExtractor().extract(
        _lines("Quê quán / Place of origin:", "Xã Hòa Bình", "Hưng Hà, Thái Bình")
    )
    assert result.fields["origin"] == "Xã Hòa Bình, Hưng Hà, Thái Bình"
    assert result.confidences["origin"] > 0.6


def test_place_names_are_corrected_from_admin_dictionary() -> None:
    result = RealFieldExtractor().extract(
        _lines("Nơi thường trú: Thôn 2, Xã Tam Kỳ, Huyện Núi Thanh, Tinh Quàng Nam")
    )
    assert result.fields["residence"] == "Thôn 2, Xã Tam Kỳ, Huyện Núi Thành, Tỉnh Quảng Nam"


# ----------------------------------------------------------------- số CCCD


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("001202000123", ("001", "Nam", 2002)),
        ("079190012345", ("079", "Nữ", 1990)),
        ("003202000123", None),  # 003 không phải mã tỉnh
        ("001299000123", None),  # năm sinh 2099 ở tương lai
        ("00120200012", None),
        ("00120200012a", None),
    ],
)
def test_decode_cccd_number(value: str, expected: tuple[str, str, int] | None) -> None:
    info = decode_cccd_number(value, today=date(2026, 10, 11))
    assert (info and (info.province_code, info.gender, info.birth_year)) == expected


def test_id_number_prefers_candidate_with_valid_cccd_structure() -> None:
    result = RealFieldExtractor().extract(_lines("Mã: 123456789012", "Số / No.: 001202000123"))
    assert result.fields["id_number"] == "001202000123"
    assert result.confidences["id_number"] > 0.9


def test_id_number_without_valid_structure_is_flagged_for_review() -> None:
    result = RealFieldExtractor().extract(_lines("Số / No.: 123456789012"))
    assert result.fields["id_number"] == "123456789012"
    assert result.confidences["id_number"] <= 0.5


def test_dob_prefers_date_matching_birth_year_in_id() -> None:
    result = RealFieldExtractor().extract(
        _lines("Số / No.: 001202000123", "01/01/1999", "Ngày sinh: 15/03/2002", "Có giá trị đến: 15/03/2027")
    )
    assert result.fields["dob"] == "15/03/2002"
    assert result.confidences["dob"] <= 0.5
    assert result.confidences["id_number"] > 0.9


def test_missing_gender_is_derived_from_id_number() -> None:
    result = RealFieldExtractor().extract(_lines("Số / No.: 079190012345"))
    assert result.fields["gender"] == "Nữ"
    assert result.confidences["gender"] == result.confidences["id_number"]


def test_gender_matching_id_number_takes_the_higher_confidence() -> None:
    result = RealFieldExtractor().extract(_lines("Số / No.: 001202000123", "Nam", prob=0.99))
    lowered = RealFieldExtractor().extract(
        [*_lines("Số / No.: 001202000123", prob=0.99), *_lines("Giới tính / Sex: Nam", prob=0.6)]
    )
    assert result.confidences["gender"] >= result.confidences["id_number"]
    assert lowered.confidences["gender"] == lowered.confidences["id_number"]


def test_id_conflicting_with_gender_and_dob_flags_all_involved_fields() -> None:
    result = RealFieldExtractor().extract(
        _lines("Số / No.: 001202000123", "Ngày sinh: 15/03/1985", "Giới tính / Sex: Nữ")
    )
    for name in ("id_number", "gender", "dob"):
        assert result.confidences[name] <= 0.5
    assert result.fields["gender"] == "Nữ"


# ----------------------------------------------------------------- pipeline


@pytest.mark.asyncio
async def test_overlong_field_is_truncated_instead_of_failing_the_image() -> None:
    response = await _pipeline(FixedExtractor(residence="Tổ 1, " * 60)).run(_png())
    assert len(response.data.residence) <= 200
    assert response.confidences["residence"] <= 0.5
    assert response.data.id_number == "001202000123"


@pytest.mark.asyncio
async def test_invalid_field_falls_back_to_placeholder() -> None:
    response = await _pipeline(FixedExtractor(dob="31/02/2001", gender="X")).run(_png())
    assert response.data.dob == FIELD_PLACEHOLDERS["dob"]
    assert response.confidences["dob"] == 0.0
    assert response.confidences["gender"] == 0.0
    assert response.confidences["full_name"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_unexpected_stage_error_hides_internal_details() -> None:
    class Broken:
        def align(self, image: Any) -> Any:
            raise RuntimeError("cuda driver exploded at 0xdeadbeef")

    with pytest.raises(OCRFailedError) as exc_info:
        await _pipeline(aligner=Broken()).run(_png())
    assert exc_info.value.code == "ocr_engine_crashed"
    assert "deadbeef" not in exc_info.value.message


@pytest.mark.asyncio
async def test_debug_artifacts_are_saved_when_a_stage_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingAligner:
        def align(self, image: Any) -> Any:
            raise OCRStageError("aligner", "no corners")

    monkeypatch.setattr(settings, "ocr_debug_save", True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(OCRFailedError):
        await _pipeline(aligner=FailingAligner()).run(_png())

    runs = list((tmp_path / "debug_images").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "01_input_bgr.png").exists()
    assert "no corners" in (runs[0] / "05_result.json").read_text(encoding="utf-8")


# ------------------------------------------------------------------- stages


def test_reading_order_groups_boxes_on_the_same_row() -> None:
    right_higher = BBox(400, 100, 600, 130)
    left_lower = BBox(10, 104, 200, 134)
    next_row = BBox(10, 160, 300, 190)
    assert _reading_order([next_row, right_higher, left_lower]) == [
        left_lower,
        right_higher,
        next_row,
    ]


def test_cleaner_accepts_even_or_zero_kernel_sizes_from_env() -> None:
    cleaner = RealImageCleaner(shadow_kernel_size=0, background_blur=20, smooth_kernel_size=4)
    out = cleaner.clean(np.full((60, 90, 3), 128, dtype=np.uint8))
    assert out.shape == (60, 90, 3)


def test_cleaner_reports_empty_image_as_stage_error() -> None:
    with pytest.raises(OCRStageError):
        RealImageCleaner().clean(np.zeros((0, 0, 3), dtype=np.uint8))


def test_aligner_rejects_self_intersecting_corners() -> None:
    crossed = {
        "top_left": (0, 0),
        "top_right": (100, 60),
        "bot_right": (100, 0),
        "bot_left": (0, 60),
    }
    with pytest.raises(OCRStageError):
        RealCardAligner._warp_perspective(np.zeros((80, 120, 3), dtype=np.uint8), crossed)


def test_mask_id_number() -> None:
    assert mask_id_number("001202000123") == "001******123"
    assert mask_id_number(None) == "-"


def test_detector_converts_paddle_results_with_numpy_scores() -> None:
    from app.services.ocr.stages.detector import RealTextDetector

    detector = object.__new__(RealTextDetector)
    detector.padding = 2
    detector.conf_threshold = 0.3
    quad = lambda x1, y1, x2, y2: [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]  # noqa: E731
    results = [
        {
            "res": {
                "dt_polys": np.array([quad(300, 10, 400, 30), quad(10, 12, 200, 32), quad(5, 80, 90, 100)]),
                "dt_scores": np.array([0.9, 0.8, 0.1]),
            }
        }
    ]
    boxes = detector._results_to_bboxes(results, np.zeros((120, 500, 3), dtype=np.uint8))
    assert [(b.xmin, b.ymin) for b in boxes] == [(8, 10), (298, 8)]


def test_residence_box_split_on_label_row_is_joined_even_when_read_after_next_line() -> None:
    lines = [
        TextLine(text="Nơi thường trú / Place of residence: 1", bbox=BBox(0, 100, 480, 118)),
        TextLine(text="Phường 5, Quận 3, TP. Hồ Chí Minh", bbox=BBox(0, 140, 500, 158)),
        TextLine(text="12/34 Lê Lợi", bbox=BBox(450, 102, 700, 120)),
    ]
    result = RealFieldExtractor().extract(lines)
    assert result.fields["residence"] == "12/34 Lê Lợi, Phường 5, Quận 3, TP. Hồ Chí Minh"


@pytest.mark.parametrize(
    "label_line",
    [
        "Nơi thường trú",
        "Noi thuong trai",
        "Nơi thương trà",
        "Nơi thường trờ/ Pace clionce",
        "Nơi thường tru, Place of madence",
        "Nơi thường trù/Place of rasidence",
        "Noi thường trù pincecresdence",
    ],
)
def test_misread_residence_label_does_not_leak_into_address(label_line: str) -> None:
    lines = [
        TextLine(text=f"{label_line} Thôn 2, Xã Tam Kỳ", bbox=BBox(0, 0, 600, 18)),
        TextLine(text="Huyện Núi Thành, Tỉnh Quảng Nam", bbox=BBox(0, 20, 600, 38)),
    ]
    result = RealFieldExtractor().extract(lines)
    assert result.fields["residence"] == "Thôn 2, Xã Tam Kỳ, Huyện Núi Thành, Tỉnh Quảng Nam"


def test_house_number_glued_to_misread_label_is_kept() -> None:
    lines = [
        TextLine(text="Noi thuong trai Place cinsidonce12/3a Thôn 2, Xã Tam Kỳ", bbox=BBox(0, 0, 600, 18)),
        TextLine(text="Huyện Núi Thành, Tỉnh Quảng Nam", bbox=BBox(0, 20, 600, 38)),
    ]
    assert RealFieldExtractor().extract(lines).fields["residence"].startswith("12/3a Thôn 2, Xã Tam Kỳ")


# ----------------------------------------------------------------- ký tự yếu, hạn thẻ


def _weak_line(text: str, weak_word: str, y: int) -> TextLine:
    chars = [0.99] * len(text)
    chars[text.index(weak_word) + 1] = 0.3
    return TextLine(text=text, bbox=BBox(0, y, 600, y + 18), recognizer_confidence=0.95, char_confidences=tuple(chars))


def test_one_weak_character_flags_text_field_despite_high_line_confidence() -> None:
    lines = [
        TextLine(text="Họ và tên / Full name:", bbox=BBox(0, 0, 600, 18)),
        _weak_line("NGUYỄN VĂN AN", "VĂN", 20),
        _weak_line("Nơi thường trú: 12 Lê Lợi, Xã Tam Kỳ", "Lợi", 40),
        TextLine(text="Huyện Núi Thành, Tỉnh Quảng Nam", bbox=BBox(0, 60, 600, 78)),
    ]
    result = RealFieldExtractor().extract(lines)
    assert result.confidences["full_name"] <= 0.5
    assert result.confidences["residence"] <= 0.5


def test_weak_character_in_dictionary_verified_place_is_not_flagged() -> None:
    lines = [
        TextLine(text="Nơi thường trú: Thôn 2, Xã Tam Kỳ", bbox=BBox(0, 0, 600, 18), recognizer_confidence=0.95),
        _weak_line("Huyện Núi Thành, Tỉnh Quảng Nam", "Quảng", 20),
    ]
    assert RealFieldExtractor().extract(lines).confidences["residence"] >= 0.85


def test_dob_disagreeing_with_expiry_birthday_is_flagged() -> None:
    ok = RealFieldExtractor().extract(_lines("Ngày sinh: 15/03/1985", "Có giá trị đến: 15/03/2025"))
    bad = RealFieldExtractor().extract(_lines("Ngày sinh: 16/03/1985", "Có giá trị đến: 15/03/2025"))
    not_milestone = RealFieldExtractor().extract(_lines("Ngày sinh: 16/03/1985", "15/03/2021"))
    assert ok.confidences["dob"] > 0.9
    assert bad.confidences["dob"] <= 0.5 and bad.confidences["expiry_date"] <= 0.5
    assert not_milestone.confidences["dob"] > 0.9


def test_expiry_is_never_the_dob_itself() -> None:
    result = RealFieldExtractor().extract(_lines("Số / No.: 001202000123", "Ngày sinh: 15/03/2002", "01/01/1999"))
    assert result.fields["dob"] == "15/03/2002"
    assert "expiry_date" not in result.fields


# ----------------------------------------------------------------- cắt xoay dòng nghiêng, số CCCD dính


def _tilted(cx: float, cy: float, w: float, h: float, deg: float) -> list[list[float]]:
    rad = np.radians(deg)
    ux, uy, vx, vy = np.cos(rad), np.sin(rad), -np.sin(rad), np.cos(rad)
    return [
        [cx + sx * w / 2 * ux + sy * h / 2 * vx, cy + sx * w / 2 * uy + sy * h / 2 * vy]
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]


def test_detector_keeps_quad_only_for_moderately_tilted_lines() -> None:
    from app.services.ocr.stages.detector import RealTextDetector

    detector = object.__new__(RealTextDetector)
    detector.padding = 2
    detector.conf_threshold = 0.3
    polys = np.array([_tilted(150, 40, 200, 20, 0.5), _tilted(150, 120, 200, 20, 5), _tilted(150, 220, 200, 20, 30)])
    results = [{"res": {"dt_polys": polys, "dt_scores": np.array([0.9, 0.9, 0.9])}}]
    boxes = detector._results_to_bboxes(results, np.zeros((300, 400, 3), dtype=np.uint8))
    assert [b.quad is not None for b in boxes] == [False, True, False]
    tl, tr, br, bl = boxes[1].quad
    assert tl[0] < tr[0] and bl[0] < br[0] and tl[1] < bl[1] and tr[1] < br[1]
    assert tr[1] > tl[1]  # nghiêng xuống bên phải như dòng gốc


def test_recognizer_straightens_tilted_line_crop() -> None:
    from app.services.ocr.stages.recognizer import RealTextRecognizer

    image = np.zeros((200, 300, 3), dtype=np.uint8)
    quad = _tilted(150, 100, 200, 30, 6)
    cv2.fillPoly(image, [np.int32(quad)], (255, 255, 255))
    box = BBox(0, 0, 300, 200, quad=tuple(tuple(p) for p in quad))
    crop = RealTextRecognizer._safe_crop(image, box)
    assert abs(crop.shape[0] - 30) <= 1 and abs(crop.shape[1] - 200) <= 1
    assert crop[3:-3, 3:-3].min() > 200  # chỉ còn dòng chữ, không lẫn nền xung quanh


def test_id_glued_to_another_number_is_split_when_unambiguous() -> None:
    glued = RealFieldExtractor().extract(_lines("Số CMND/CCCD: 1234567891001202000123"))
    assert glued.fields["id_number"] == "001202000123"
    assert glued.confidences["id_number"] <= 0.5
    ambiguous = RealFieldExtractor().extract(_lines("Số: 001202000123079190012345"))
    assert ambiguous.confidences["id_number"] == 0
