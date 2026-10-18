from __future__ import annotations

from typing import Any

import pytest

from app.core.exceptions import OCRFailedError
from app.services.ocr.interfaces import ExtractionResult, OCRStageError, TextLine
from app.services.ocr.pipeline import OCRPipeline
from app.services.ocr.stages import (
    MockAligner,
    MockCleaner,
    MockDetector,
    MockExtractor,
    MockRecognizer,
)


def _make_png_bytes() -> bytes:
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    image = np.zeros((96, 160, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Failed to encode test image")
    return encoded.tobytes()


class EmptyDetector:
    def detect(self, image: Any) -> list[Any]:
        _ = image
        return []


class FailingAligner:
    def align(self, image: Any) -> Any:
        _ = image
        raise OCRStageError("aligner", "forced aligner failure")


class OutOfRangeConfidenceExtractor:
    def extract(self, lines: list[TextLine]) -> ExtractionResult:
        _ = lines
        return ExtractionResult(
            fields={
                "id_number": "001202000123",
                "full_name": "NGUYEN VAN A",
                "dob": "01/01/2002",
                "gender": "Nam",
                "nationality": "Viet Nam",
                "origin": "Quan 1, TP HCM",
                "residence": "123 Le Loi, Quan 1, TP HCM",
                "expiry_date": "01/01/2030",
            },
            confidences={
                "id_number": -1.2,
                "full_name": 2.4,
            },
        )


@pytest.mark.asyncio
async def test_pipeline_full_mock_success() -> None:
    pipeline = OCRPipeline(
        aligner=MockAligner(),
        cleaner=MockCleaner(),
        detector=MockDetector(),
        recognizer=MockRecognizer(),
        extractor=MockExtractor(),
    )

    result = await pipeline.run(_make_png_bytes())

    assert result.data.id_number == "001202000123"
    assert "full_name" in result.data.model_dump()
    assert 0.0 <= result.confidences["id_number"] <= 1.0


@pytest.mark.asyncio
async def test_pipeline_raises_when_detector_finds_no_boxes() -> None:
    pipeline = OCRPipeline(
        aligner=MockAligner(),
        cleaner=MockCleaner(),
        detector=EmptyDetector(),
        recognizer=MockRecognizer(),
        extractor=MockExtractor(),
    )

    with pytest.raises(OCRFailedError) as exc_info:
        await pipeline.run(_make_png_bytes())

    assert exc_info.value.code == "ocr_detector_failed"


@pytest.mark.asyncio
async def test_pipeline_maps_stage_error_to_domain_error_code() -> None:
    pipeline = OCRPipeline(
        aligner=FailingAligner(),
        cleaner=MockCleaner(),
        detector=MockDetector(),
        recognizer=MockRecognizer(),
        extractor=MockExtractor(),
    )

    with pytest.raises(OCRFailedError) as exc_info:
        await pipeline.run(_make_png_bytes())

    assert exc_info.value.code == "ocr_aligner_failed"
    assert "forced aligner failure" in exc_info.value.message


@pytest.mark.asyncio
async def test_pipeline_clamps_confidence_values_to_0_1() -> None:
    pipeline = OCRPipeline(
        aligner=MockAligner(),
        cleaner=MockCleaner(),
        detector=MockDetector(),
        recognizer=MockRecognizer(),
        extractor=OutOfRangeConfidenceExtractor(),
    )

    result = await pipeline.run(_make_png_bytes())

    assert result.confidences["id_number"] == 0.0
    assert result.confidences["full_name"] == 1.0
    assert result.confidences["dob"] == 0.0


@pytest.mark.asyncio
async def test_recognizer_reads_color_aligned_image_detector_reads_cleaned() -> None:
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    color = np.zeros((96, 160, 3), dtype=np.uint8)
    color[:, :] = (255, 0, 0)
    ok, encoded = cv2.imencode(".png", color)
    assert ok
    seen: dict[str, Any] = {}

    class GrayCleaner:
        def clean(self, image: Any) -> Any:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

    class SpyDetector(MockDetector):
        def detect(self, image: Any) -> list[Any]:
            seen["detect"] = image
            return super().detect(image)

    class SpyRecognizer(MockRecognizer):
        def recognize(self, image: Any, boxes: list[Any]) -> list[TextLine]:
            seen["recognize"] = image
            return super().recognize(image, boxes)

    pipeline = OCRPipeline(
        aligner=MockAligner(),
        cleaner=GrayCleaner(),
        detector=SpyDetector(),
        recognizer=SpyRecognizer(),
        extractor=MockExtractor(),
    )

    await pipeline.run(encoded.tobytes())

    assert tuple(seen["recognize"][0, 0]) == (0, 0, 255)
    detect_px = seen["detect"][0, 0]
    assert detect_px[0] == detect_px[1] == detect_px[2]
