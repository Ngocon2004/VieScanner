"""OCR engine entry point – wrap `OCRPipeline` để các endpoint sử dụng.

Engine được build 1 lần (lru_cache) và inject vào FastAPI route qua
`Depends(get_ocr_engine)`. Configuration đọc từ `settings.ocr_engine`:

- `mock`: full mock pipeline – không cần ML stack.
- `real`: full real pipeline – Phase 2.1-2.5 sẽ implement.
- `hybrid`: dev mode – mix mock + real để debug từng stage.

Để test/override engine trong unit test, dùng:
    app.dependency_overrides[get_ocr_engine] = lambda: my_test_engine
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import settings
from app.core.exceptions import OCRFailedError
from app.core.logging import logger
from app.models.cccd import CCCDData, CCCDExtractResponse
from app.repositories import ModelWeightsRepository
from app.services.ocr.pipeline import OCRPipeline
from app.services.ocr.stages import (
    MockAligner,
    MockCleaner,
    MockDetector,
    MockExtractor,
    MockRecognizer,
    RealCardAligner,
    RealFieldExtractor,
    RealImageCleaner,
    RealTextDetector,
    RealTextRecognizer,
)


class OCREngine(Protocol):
    """Interface cho engine OCR cấp cao (wrap toàn pipeline)."""

    async def extract(
        self, image_bytes: bytes
    ) -> CCCDExtractResponse:  # pragma: no cover
        ...


class _PipelineEngine:
    """Adapter biến `OCRPipeline.run` thành interface OCREngine."""

    def __init__(self, pipeline: OCRPipeline) -> None:
        self._pipeline = pipeline

    async def extract(self, image_bytes: bytes) -> CCCDExtractResponse:
        return await self._pipeline.run(image_bytes)


def _build_mock_pipeline() -> OCRPipeline:
    return OCRPipeline(
        aligner=MockAligner(),
        cleaner=MockCleaner(),
        detector=MockDetector(),
        recognizer=MockRecognizer(),
        extractor=MockExtractor(),
    )


def _build_real_pipeline() -> OCRPipeline:
    """Build pipeline tốt nhất hiện có – tất cả 5 stages đều REAL từ Phase 2.5.

    Hiện trạng (Phase 2.5 – pipeline FULL REAL):
      ① Aligner    : REAL (YOLO model_crop.pt – 4-corner detect + warp)
      ② Cleaner    : REAL (OpenCV shadow removal + auto contrast)
      ③ Detector   : REAL (PaddleOCR PP-OCRv5_*_det)
      ④ Recognizer : REAL (VietOCR vgg_transformer / vgg_seq2seq)
      ⑤ Extractor  : REAL (Rule-based regex + label-matching + fuzzy)
    """
    weights = ModelWeightsRepository()
    aligner_path = str(weights.require_path("card_aligner"))
    logger.info(
        "Building real pipeline | aligner=YOLO(conf={},retries={}) | cleaner=Real(k={},clip={}) | "
        "detector={} (conf={},pad={}) | recognizer={} (beamsearch={}) | extractor=Rule(fuzzy={})",
        settings.ocr_aligner_conf_threshold,
        settings.ocr_aligner_retry_conf_thresholds,
        settings.ocr_cleaner_shadow_kernel_size,
        settings.ocr_cleaner_clip_hist_percent,
        settings.ocr_detector_model,
        settings.ocr_detector_conf_threshold,
        settings.ocr_detector_padding,
        settings.ocr_recognizer_model,
        settings.ocr_recognizer_beamsearch,
        settings.ocr_extractor_fuzzy_threshold,
    )
    return OCRPipeline(
        aligner=RealCardAligner(
            model_path=aligner_path,
            device=settings.ocr_device,
            conf_threshold=settings.ocr_aligner_conf_threshold,
            retry_conf_thresholds=tuple(settings.ocr_aligner_retry_conf_thresholds),
        ),
        cleaner=RealImageCleaner(
            shadow_kernel_size=settings.ocr_cleaner_shadow_kernel_size,
            clip_hist_percent=settings.ocr_cleaner_clip_hist_percent,
        ),
        detector=RealTextDetector(
            model_name=settings.ocr_detector_model,
            device=settings.ocr_device,
            conf_threshold=settings.ocr_detector_conf_threshold,
            padding=settings.ocr_detector_padding,
        ),
        recognizer=RealTextRecognizer(
            model_name=settings.ocr_recognizer_model,
            device=settings.ocr_device,
            beamsearch=settings.ocr_recognizer_beamsearch,
        ),
        extractor=RealFieldExtractor(
            fuzzy_threshold=settings.ocr_extractor_fuzzy_threshold,
        ),
    )


@lru_cache(maxsize=1)
def _build_engine() -> OCREngine:
    """Khởi tạo OCR engine 1 lần / process dựa theo settings."""
    engine_type = settings.ocr_engine.lower()
    logger.info(
        "Initializing OCR engine | type={} | device={}",
        engine_type,
        settings.ocr_device,
    )

    if engine_type == "mock":
        return _PipelineEngine(_build_mock_pipeline())
    if engine_type == "real":
        return _PipelineEngine(_build_real_pipeline())
    if engine_type == "hybrid":
        # Hybrid để implement sau (Phase 2.0+) – tạm fallback mock.
        logger.warning("hybrid engine chưa hỗ trợ; fallback mock.")
        return _PipelineEngine(_build_mock_pipeline())

    raise OCRFailedError(
        f"Unknown OCR_ENGINE={engine_type!r}. Hợp lệ: mock | real | hybrid.",
        code="ocr_engine_invalid",
    )


def get_ocr_engine() -> OCREngine:
    """FastAPI dependency – inject engine vào route."""
    return _build_engine()


# Backward-compat: hàm cũ vẫn còn để các test/legacy code import.
async def extract_cccd_info(image_bytes: bytes) -> CCCDData:
    """Deprecated: dùng `Depends(get_ocr_engine)` thay thế."""
    result = await _build_engine().extract(image_bytes)
    return result.data


__all__ = [
    "OCREngine",
    "get_ocr_engine",
    "extract_cccd_info",
]
