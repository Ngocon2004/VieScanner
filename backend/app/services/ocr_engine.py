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

import asyncio
import threading
from functools import lru_cache
from time import perf_counter
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
    RealOrientationClassifier,
    RealTextDetector,
    RealTextRecognizer,
)


class OCREngine(Protocol):
    """Interface cho engine OCR cấp cao (wrap toàn pipeline)."""

    async def extract(
        self, image_bytes: bytes
    ) -> CCCDExtractResponse:  # pragma: no cover
        ...


# ─────────────────────────────────────────────────────────────────────────────
# M1 – Semaphore giới hạn số OCR chạy song song
# ─────────────────────────────────────────────────────────────────────────────
# `OCRPipeline.run` đẩy phần inference nặng sang thread (`asyncio.to_thread`).
# Model (YOLO/Paddle/VietOCR) là singleton dùng chung và KHÔNG thread-safe nên
# nhiều request chạy song song trên cùng instance dễ crash / OOM GPU. Semaphore
# này giới hạn số lần `extract` chạy đồng thời (env `OCR_MAX_CONCURRENCY`).
#
# Semaphore phải gắn với event loop đang chạy. Vì test (pytest-asyncio,
# loop-scope=function) tạo loop mới mỗi test, ta tạo lại semaphore khi loop đổi
# để tránh lỗi "bound to a different event loop"; ở production loop là duy nhất
# nên semaphore cũng chỉ tạo 1 lần.
_ocr_semaphore: asyncio.Semaphore | None = None
_ocr_semaphore_loop: asyncio.AbstractEventLoop | None = None


def _get_ocr_semaphore() -> asyncio.Semaphore:
    global _ocr_semaphore, _ocr_semaphore_loop
    loop = asyncio.get_running_loop()
    if _ocr_semaphore is None or _ocr_semaphore_loop is not loop:
        limit = max(1, int(settings.ocr_max_concurrency))
        _ocr_semaphore = asyncio.Semaphore(limit)
        _ocr_semaphore_loop = loop
        logger.debug("OCR semaphore created | limit={}", limit)
    return _ocr_semaphore


def get_ocr_semaphore() -> asyncio.Semaphore:
    return _get_ocr_semaphore()


class _PipelineEngine:
    """Adapter biến `OCRPipeline.run` thành interface OCREngine."""

    def __init__(self, pipeline: OCRPipeline) -> None:
        self._pipeline = pipeline

    async def extract(self, image_bytes: bytes) -> CCCDExtractResponse:
        async with _get_ocr_semaphore():
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
        "detector={} (conf={},pad={}) | recognizer={} (beamsearch={},batch={}) | extractor=Rule(fuzzy={})",
        settings.ocr_aligner_conf_threshold,
        settings.ocr_aligner_retry_conf_thresholds,
        settings.ocr_cleaner_shadow_kernel_size,
        settings.ocr_cleaner_clip_hist_percent,
        settings.ocr_detector_model,
        settings.ocr_detector_conf_threshold,
        settings.ocr_detector_padding,
        settings.ocr_recognizer_model,
        settings.ocr_recognizer_beamsearch,
        settings.ocr_recognizer_batch,
        settings.ocr_extractor_fuzzy_threshold,
    )
    return OCRPipeline(
        aligner=RealCardAligner(
            model_path=aligner_path,
            device=settings.ocr_device,
            conf_threshold=settings.ocr_aligner_conf_threshold,
            retry_conf_thresholds=tuple(settings.ocr_aligner_retry_conf_thresholds),
            contour_fallback=settings.ocr_aligner_contour_fallback,
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
            batch=settings.ocr_recognizer_batch,
        ),
        extractor=RealFieldExtractor(
            fuzzy_threshold=settings.ocr_extractor_fuzzy_threshold,
        ),
        orientation=(
            RealOrientationClassifier(model_name=settings.ocr_orientation_model, device=settings.ocr_device)
            if settings.ocr_orientation_retry
            else None
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


_build_lock = threading.Lock()


def get_ocr_engine() -> OCREngine:
    """FastAPI dependency – inject engine vào route."""
    global _engine_ready
    # lru_cache không khóa: nhiều thread build cùng lúc sẽ nạp model nhiều lần (OOM GPU).
    with _build_lock:
        engine = _build_engine()
    _engine_ready = True
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# M2/M3 – Warm-up models lúc startup + readiness flag
# ─────────────────────────────────────────────────────────────────────────────
# Build engine = load YOLO/Paddle/VietOCR (các stage real pre-warm weights ngay
# trong __init__). Nếu chỉ lazy-load ở request đầu thì request đó rất chậm. Ta
# warm trong `lifespan` (chạy phần nặng ở thread để không block event loop).
_engine_ready: bool = False


def is_ocr_engine_ready() -> bool:
    """True nếu engine đã build xong (model đã nạp). Dùng cho /health."""
    return _engine_ready


async def warmup_ocr_engine() -> bool:
    """Pre-build engine để nạp model trước, tránh request đầu chậm.

    Best-effort: lỗi (vd thiếu weights) chỉ log cảnh báo và để lazy-load thử lại
    ở request đầu — không chặn app khởi động. Trả về True nếu warm-up thành công.
    """
    global _engine_ready
    engine_type = settings.ocr_engine.lower()
    started = perf_counter()
    try:
        # `_build_engine` (đồng bộ, nặng với real) chạy trong thread.
        await asyncio.to_thread(get_ocr_engine)
        if engine_type == "real":
            from app.services.ocr.address import preload_admin_units

            await asyncio.to_thread(preload_admin_units)
        logger.info(
            "OCR engine warm-up done | type={} | {:.2f}s",
            engine_type,
            perf_counter() - started,
        )
        return True
    except Exception as exc:  # noqa: BLE001 – không để warm-up làm chết startup.
        _engine_ready = False
        logger.warning(
            "OCR engine warm-up failed (sẽ lazy-load lại khi có request): {}", exc
        )
        return False


# Backward-compat: hàm cũ vẫn còn để các test/legacy code import.
async def extract_cccd_info(image_bytes: bytes) -> CCCDData:
    """Deprecated: dùng `Depends(get_ocr_engine)` thay thế."""
    result = await _build_engine().extract(image_bytes)
    return result.data


__all__ = [
    "OCREngine",
    "get_ocr_engine",
    "warmup_ocr_engine",
    "is_ocr_engine_ready",
    "extract_cccd_info",
]
