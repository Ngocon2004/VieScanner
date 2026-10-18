from __future__ import annotations

from typing import Any

import pytest

from app.services.ocr.card_geometry import card_region_from_headers
from app.services.ocr.interfaces import BBox, ExtractionResult, TextLine
from app.services.ocr.pipeline import OCRPipeline
from app.services.ocr.review import looks_like_back_side, residence_on_back, review_issues
from app.services.ocr.stages import MockAligner, MockCleaner, MockDetector, MockRecognizer

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

GOOD = ExtractionResult(
    fields={
        "id_number": "001202000123", "full_name": "NGUYỄN VĂN AN", "dob": "01/01/2002", "gender": "Nam",
        "nationality": "Việt Nam", "origin": "Hưng Hà, Thái Bình", "residence": "Thôn 2, Xã Tam Kỳ",
        "expiry_date": "01/01/2042",
    },
    confidences=dict.fromkeys(
        ("id_number", "full_name", "dob", "gender", "nationality", "origin", "residence", "expiry_date"), 0.9
    ),
)
POOR = ExtractionResult(fields={"nationality": "Việt Nam"}, confidences={"nationality": 0.9})


def _png() -> bytes:
    ok, encoded = cv2.imencode(".png", np.zeros((96, 160, 3), dtype=np.uint8))
    assert ok
    return encoded.tobytes()


class SequenceExtractor:
    def __init__(self, *results: ExtractionResult) -> None:
        self.results = list(results)
        self.calls = 0

    def extract(self, lines: list[TextLine]) -> ExtractionResult:
        self.calls += 1
        result = self.results.pop(0)
        return ExtractionResult(fields=dict(result.fields), confidences=dict(result.confidences))


class FixedOrientation:
    def __init__(self, angle: int) -> None:
        self.angle = angle
        self.calls = 0

    def predict(self, image: Any) -> int:
        self.calls += 1
        return self.angle


def _pipeline(extractor: SequenceExtractor, orientation: FixedOrientation | None) -> OCRPipeline:
    return OCRPipeline(
        aligner=MockAligner(), cleaner=MockCleaner(), detector=MockDetector(),
        recognizer=MockRecognizer(), extractor=extractor, orientation=orientation,
    )


@pytest.mark.asyncio
async def test_poor_result_is_retried_rotated_and_better_result_kept() -> None:
    extractor, orientation = SequenceExtractor(POOR, GOOD), FixedOrientation(90)
    response = await _pipeline(extractor, orientation).run(_png())
    assert orientation.calls == 1 and extractor.calls == 2
    assert response.data.full_name == "NGUYỄN VĂN AN"
    assert response.quality is None


@pytest.mark.asyncio
async def test_good_result_skips_orientation() -> None:
    extractor, orientation = SequenceExtractor(GOOD), FixedOrientation(90)
    await _pipeline(extractor, orientation).run(_png())
    assert orientation.calls == 0


@pytest.mark.asyncio
async def test_rotation_not_better_keeps_original_and_flags_review() -> None:
    extractor, orientation = SequenceExtractor(POOR, POOR), FixedOrientation(270)
    response = await _pipeline(extractor, orientation).run(_png())
    assert extractor.calls == 2
    assert response.quality is not None
    assert [issue.code for issue in response.quality.issues] == ["few_fields_read"]


@pytest.mark.asyncio
async def test_upright_prediction_does_not_rerun_ocr() -> None:
    extractor, orientation = SequenceExtractor(POOR), FixedOrientation(0)
    await _pipeline(extractor, orientation).run(_png())
    assert extractor.calls == 1


def _line(text: str) -> TextLine:
    return TextLine(text=text, bbox=BBox(0, 0, 10, 10))


def test_back_side_detected_from_mrz_or_labels_without_name() -> None:
    assert looks_like_back_side([_line("IDVNM0012020001<<<<")], {})
    assert looks_like_back_side([_line("Đặc điểm nhân dạng: Sẹo chấm")], {"dob": 0.9})
    assert not looks_like_back_side([_line("IDVNM0012020001<<<<")], {"full_name": 0.9})
    assert not looks_like_back_side([_line("Họ và tên")], {})


def test_review_issues() -> None:
    assert [i.code for i in review_issues({}, back_side=True)] == ["back_side"]
    assert [i.code for i in review_issues({"dob": 0.9, "gender": 0.9})] == ["few_fields_read"]
    assert review_issues(GOOD.confidences) == []
    assert all(i.severity == "soft" for i in review_issues({}))


# ----------------------------------------------------------------- thẻ nằm trong ảnh trang


PAGE = (1280, 960, 3)


def test_no_crop_when_card_fills_image() -> None:
    assert card_region_from_headers([BBox(300, 20, 900, 50)], (600, 950, 3)) is None
    assert card_region_from_headers([], PAGE) is None


def test_card_region_from_small_header_on_page() -> None:
    region = card_region_from_headers([BBox(400, 500, 600, 520), BBox(420, 525, 580, 545)], PAGE)
    assert region is not None and region.cards_on_page == 1
    x0, y0, x1, y1 = region.box
    assert x0 < 400 < 600 < x1 and y0 < 500 and y1 > 545 + 100


def test_second_card_on_page_is_counted_and_cut_off() -> None:
    region = card_region_from_headers([BBox(400, 100, 600, 120), BBox(400, 700, 600, 720)], PAGE)
    assert region is not None and region.cards_on_page == 2
    assert region.box[3] < 700




class HeaderRecognizer(MockRecognizer):
    """Lần OCR đầu (cả trang) trả 1 dòng tiêu đề nhỏ; lần sau (vùng cắt) trả như mock."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def recognize(self, image: Any, boxes: list[Any]) -> list[TextLine]:
        self.calls += 1
        if self.calls == 1:
            return [TextLine(text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", bbox=BBox(70, 10, 110, 14))]
        return super().recognize(image, boxes)


@pytest.mark.asyncio
async def test_page_without_name_is_recropped_by_header() -> None:
    page_result = ExtractionResult(
        fields={**GOOD.fields, "full_name": ""}, confidences={**GOOD.confidences, "full_name": 0.0}
    )
    extractor = SequenceExtractor(page_result, GOOD)
    pipeline = OCRPipeline(
        aligner=MockAligner(), cleaner=MockCleaner(), detector=MockDetector(),
        recognizer=HeaderRecognizer(), extractor=extractor,
    )
    response = await pipeline.run(_png())
    assert extractor.calls == 2
    assert response.data.full_name == "NGUYỄN VĂN AN"


class TwoCardRecognizer(MockRecognizer):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def recognize(self, image: Any, boxes: list[Any]) -> list[TextLine]:
        self.calls += 1
        if self.calls == 1:
            return [
                TextLine(text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", bbox=BBox(70, 5, 110, 9)),
                TextLine(text="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", bbox=BBox(70, 60, 110, 64)),
            ]
        return super().recognize(image, boxes)


@pytest.mark.asyncio
async def test_multi_card_page_reads_first_card_even_when_name_found() -> None:
    other_person = ExtractionResult(
        fields={**GOOD.fields, "id_number": "079203000456", "full_name": "TRẦN THỊ B"},
        confidences=dict(GOOD.confidences),
    )
    extractor = SequenceExtractor(other_person, GOOD)
    pipeline = OCRPipeline(
        aligner=MockAligner(), cleaner=MockCleaner(), detector=MockDetector(),
        recognizer=TwoCardRecognizer(), extractor=extractor,
    )
    response = await pipeline.run(_png())
    assert response.data.full_name == "NGUYỄN VĂN AN"
    assert response.quality is not None
    assert [i.code for i in response.quality.issues] == ["multiple_cards"]


def test_front_of_2024_card_asks_for_the_back_to_get_residence() -> None:
    lines = [_line("Số định danh cá nhân / Personal identification number"), _line("NGUYỄN VĂN AN")]
    assert residence_on_back(lines, {"full_name": 0.9})
    assert not residence_on_back(lines, {"full_name": 0.9, "residence": 0.9})
    assert not residence_on_back([*lines, _line("Quê quán / Place of origin")], {"full_name": 0.9})
    issues = review_issues({"full_name": 0.9, "id_number": 0.9, "dob": 0.9, "gender": 0.9}, residence_on_back=True)
    assert [i.code for i in issues] == ["residence_on_back"]


def test_back_side_message_only_asks_for_what_is_still_missing() -> None:
    assert "nơi thường trú" in review_issues({}, back_side=True)[0].message
    assert "nơi thường trú" not in review_issues({"residence": 0.8}, back_side=True)[0].message
