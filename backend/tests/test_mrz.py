from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.services.ocr.interfaces import BBox, TextLine
from app.services.ocr.mrz import _check_digit, read_mrz
from app.services.ocr.pipeline import OCRPipeline
from app.services.ocr.stages import MockAligner, MockCleaner, MockDetector, RealFieldExtractor

ID = "001200012345"
DOC = ID[3:]
TODAY = date(2026, 10, 14)


def _back_side_texts(*, dob: str = "000315", sex: str = "M", expiry: str = "400315") -> list[str]:
    # VietOCR bỏ mất `<` và đọc số 0 thành chữ O ở dòng 1.
    line1 = f"IDVNM{DOC}{_check_digit(DOC)}{ID}6".replace("0", "O", 2)
    line2 = f"{dob}{_check_digit(dob)}{sex}{expiry}{_check_digit(expiry)}VNM8"
    return ["Đặc điểm nhân dạng: Nốt ruồi", line1, line2, "NGUYENVANAN"]


def test_check_digit_matches_icao_9303_examples() -> None:
    assert _check_digit("740812") == "2"
    assert _check_digit("120415") == "9"


def test_reads_checksummed_fields_without_chevrons() -> None:
    mrz = read_mrz(_back_side_texts(), today=TODAY)
    assert mrz is not None
    assert mrz.to_fields() == {
        "id_number": ID, "dob": "15/03/2000", "gender": "Nam", "expiry_date": "15/03/2040", "nationality": "Việt Nam",
    }


def test_wrong_check_digits_are_ignored() -> None:
    texts = [f"IDVNM{DOC}{(int(_check_digit(DOC)) + 1) % 10}{ID}", "0003150M4003150VNM"]
    assert read_mrz(texts, today=TODAY) is None


def test_birth_century_without_id_number() -> None:
    mrz = read_mrz(_back_side_texts(dob="850101", sex="F")[2:], today=TODAY)
    assert mrz is not None and mrz.id_number is None
    assert (mrz.dob, mrz.gender) == ("01/01/1985", "Nữ")


class FixedRecognizer:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts

    def recognize(self, image: Any, boxes: list[BBox]) -> list[TextLine]:
        return [TextLine(text=t, bbox=BBox(0, 20 * i, 300, 20 * i + 18)) for i, t in enumerate(self.texts)]


@pytest.mark.asyncio
async def test_pipeline_fills_back_side_fields_from_mrz() -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    ok, png = cv2.imencode(".png", np.zeros((96, 160, 3), dtype=np.uint8))
    assert ok
    pipeline = OCRPipeline(
        aligner=MockAligner(), cleaner=MockCleaner(), detector=MockDetector(),
        recognizer=FixedRecognizer(_back_side_texts()), extractor=RealFieldExtractor(),
    )
    response = await pipeline.run(png.tobytes())
    assert response.data.id_number == ID
    assert response.data.expiry_date == "15/03/2040"
    assert response.confidences["id_number"] == 1.0
    assert response.confidences["full_name"] == 0.0
    assert response.quality is not None
    issue = response.quality.issues[0]
    assert issue.code == "back_side" and "MRZ" in issue.message


@pytest.mark.asyncio
async def test_back_side_issue_date_is_not_taken_as_dob() -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    ok, png = cv2.imencode(".png", np.zeros((96, 160, 3), dtype=np.uint8))
    assert ok
    texts = ["Đặc điểm nhân dạng: Nốt ruồi", "Ngày, tháng, năm: 10/08/2021"]
    pipeline = OCRPipeline(
        aligner=MockAligner(), cleaner=MockCleaner(), detector=MockDetector(),
        recognizer=FixedRecognizer(texts), extractor=RealFieldExtractor(),
    )
    response = await pipeline.run(png.tobytes())
    assert response.data.dob != "10/08/2021"
    assert response.confidences["dob"] == 0.0


def test_line2_requires_nationality_after_expiry() -> None:
    line = _back_side_texts()[2]
    assert read_mrz([line], today=TODAY) is not None
    assert read_mrz([line.replace("VNM", "XYZ")], today=TODAY) is None


@pytest.mark.asyncio
async def test_back_side_without_mrz_does_not_claim_mrz() -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    ok, png = cv2.imencode(".png", np.zeros((96, 160, 3), dtype=np.uint8))
    assert ok
    pipeline = OCRPipeline(
        aligner=MockAligner(), cleaner=MockCleaner(), detector=MockDetector(),
        recognizer=FixedRecognizer(["Đặc điểm nhân dạng: Nốt ruồi", ID]), extractor=RealFieldExtractor(),
    )
    response = await pipeline.run(png.tobytes())
    assert response.quality is not None
    issue = response.quality.issues[0]
    assert issue.code == "back_side" and "MRZ" not in issue.message


class FixedExtractor:
    def __init__(self, fields: dict[str, str], confidences: dict[str, float]) -> None:
        self.fields, self.confidences = fields, confidences

    def extract(self, lines: list[TextLine]) -> Any:
        from app.services.ocr.interfaces import ExtractionResult

        return ExtractionResult(fields=dict(self.fields), confidences=dict(self.confidences))


FRONT = {
    "id_number": ID, "full_name": "NGUYỄN VĂN AN", "dob": "15/03/2000", "gender": "Nam",
    "nationality": "Việt Nam", "origin": "Hưng Hà, Thái Bình", "residence": "Thôn 2, Xã Tam Kỳ",
}


async def _run_both_sides(front_id: str) -> Any:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    ok, png = cv2.imencode(".png", np.zeros((96, 160, 3), dtype=np.uint8))
    assert ok
    extractor = FixedExtractor({**FRONT, "id_number": front_id}, dict.fromkeys(FRONT, 0.9))
    pipeline = OCRPipeline(
        aligner=MockAligner(), cleaner=MockCleaner(), detector=MockDetector(),
        recognizer=FixedRecognizer(_back_side_texts()), extractor=extractor,
    )
    return await pipeline.run(png.tobytes())


@pytest.mark.asyncio
async def test_both_sides_page_fills_expiry_from_matching_mrz() -> None:
    response = await _run_both_sides(ID)
    assert response.data.expiry_date == "15/03/2040"
    assert response.confidences["id_number"] == 1.0
    assert response.data.full_name == "NGUYỄN VĂN AN"
    assert response.quality is None


@pytest.mark.asyncio
async def test_both_sides_page_ignores_mrz_of_another_card() -> None:
    response = await _run_both_sides("001200099999")
    assert response.data.expiry_date is None
    assert response.data.id_number == "001200099999"
