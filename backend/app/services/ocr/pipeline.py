"""OCRPipeline – orchestrate 5 stage để biến ảnh -> CCCDData.

Pipeline nhận stage objects qua constructor (dependency injection), giúp:
  - Test: thay 1 stage bằng mock mà giữ nguyên các stage khác.
  - Production: thay MockX -> RealX (vd thay aligner mock -> YOLO aligner).
  - Hybrid: real cleaner + mock detector để debug từng stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import OCRFailedError
from app.core.logging import logger
from app.models.cccd import CCCDData, CCCDExtractResponse
from app.services.ocr.interfaces import (
    Aligner,
    Cleaner,
    Detector,
    Extractor,
    OCRStageError,
    Recognizer,
)

if TYPE_CHECKING:
    import numpy as np


@dataclass(slots=True)
class PipelineTrace:
    """Trace metadata cho 1 lần chạy pipeline."""

    stage_ms: dict[str, float]
    total_ms: float
    num_boxes: int
    num_lines: int
    debug_dir: str | None = None


def _decode_image(image_bytes: bytes) -> "np.ndarray":
    """Decode bytes -> BGR numpy array (OpenCV format).

    Import opencv lazily để scaffolding (mock pipeline) không bắt buộc OpenCV.
    """
    try:
        import cv2  # type: ignore[import-untyped]
        import numpy as np
    except ImportError as exc:
        logger.warning(
            "OpenCV chưa cài; trả về stub image. Cài `opencv-python-headless` "
            "khi chuyển sang real pipeline. ({})",
            exc,
        )

        class _StubImage:
            shape = (504, 800, 3)

            def __init__(self, raw: bytes) -> None:
                self._raw = raw

        return _StubImage(image_bytes)  # type: ignore[return-value]

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise OCRFailedError("Không thể decode ảnh đầu vào.")
    return img


class OCRPipeline:
    """End-to-end OCR pipeline."""

    def __init__(
        self,
        *,
        aligner: Aligner,
        cleaner: Cleaner,
        detector: Detector,
        recognizer: Recognizer,
        extractor: Extractor,
    ) -> None:
        self._aligner = aligner
        self._cleaner = cleaner
        self._detector = detector
        self._recognizer = recognizer
        self._extractor = extractor

    async def run(self, image_bytes: bytes) -> CCCDExtractResponse:
        """Async wrapper – API endpoint dùng async, pipeline xử lý sync."""
        response, _trace = self._run_sync(image_bytes)
        return response

    async def run_with_trace(self, image_bytes: bytes) -> tuple[CCCDExtractResponse, PipelineTrace]:
        """Chạy pipeline và trả thêm trace timings/debug info."""
        return self._run_sync(image_bytes)

    def _run_sync(self, image_bytes: bytes) -> tuple[CCCDExtractResponse, PipelineTrace]:
        try:
            stage_ms: dict[str, float] = {}
            total_start = perf_counter()

            t0 = perf_counter()
            image = _decode_image(image_bytes)
            stage_ms["decode"] = (perf_counter() - t0) * 1000

            logger.debug(
                "OCRPipeline start | bytes={} | shape={}",
                len(image_bytes),
                getattr(image, "shape", None),
            )

            t0 = perf_counter()
            aligned = self._aligner.align(image)
            stage_ms["align"] = (perf_counter() - t0) * 1000

            t0 = perf_counter()
            cleaned = self._cleaner.clean(aligned)
            stage_ms["clean"] = (perf_counter() - t0) * 1000

            t0 = perf_counter()
            boxes = self._detector.detect(cleaned)
            stage_ms["detect"] = (perf_counter() - t0) * 1000

            if not boxes:
                logger.warning("Detector trả về 0 box.")
                raise OCRFailedError("Không phát hiện được vùng văn bản nào.")

            t0 = perf_counter()
            lines = self._recognizer.recognize(cleaned, boxes)
            stage_ms["recognize"] = (perf_counter() - t0) * 1000

            t0 = perf_counter()
            result = self._extractor.extract(lines)
            stage_ms["extract"] = (perf_counter() - t0) * 1000

            try:
                cccd = CCCDData(**result.fields)
            except Exception as exc:  # noqa: BLE001
                logger.warning("OCR extract data không vượt qua validators: {}", exc)
                raise OCRFailedError(
                    f"Dữ liệu trích xuất không hợp lệ: {exc}"
                ) from exc

            response = CCCDExtractResponse(
                data=cccd,
                confidences=_normalize_confidences(result.confidences, cccd),
            )

            total_ms = (perf_counter() - total_start) * 1000
            rounded_stage_ms = {k: round(v, 2) for k, v in stage_ms.items()}
            bottleneck_stage = max(rounded_stage_ms, key=rounded_stage_ms.get)

            trace = PipelineTrace(
                stage_ms=rounded_stage_ms,
                total_ms=round(total_ms, 2),
                num_boxes=len(boxes),
                num_lines=len(lines),
            )

            if settings.ocr_debug_save:
                trace.debug_dir = self._save_debug_artifacts(
                    image=image,
                    aligned=aligned,
                    cleaned=cleaned,
                    boxes=boxes,
                    lines=lines,
                    response=response,
                )

            logger.info(
                "OCRPipeline success | id_number={} | total_ms={} | stage_ms={} | bottleneck={}={}ms",
                cccd.id_number,
                trace.total_ms,
                trace.stage_ms,
                bottleneck_stage,
                trace.stage_ms[bottleneck_stage],
            )
            return response, trace

        except OCRStageError as exc:
            logger.warning("Pipeline stage failed: {}", exc)
            raise OCRFailedError(exc.message, code=f"ocr_{exc.stage}_failed") from exc
        except OCRFailedError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline crashed unexpectedly")
            raise OCRFailedError(f"Lỗi không mong muốn trong OCR: {exc}") from exc

    def _save_debug_artifacts(
        self,
        *,
        image: "np.ndarray",
        aligned: "np.ndarray",
        cleaned: "np.ndarray",
        boxes: list[Any],
        lines: list[Any],
        response: CCCDExtractResponse,
    ) -> str | None:
        """Lưu ảnh trung gian + annotation để debug OCR."""
        try:
            import cv2  # type: ignore[import-untyped]
            import numpy as np
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR_DEBUG_SAVE=true nhưng import cv2 fail: {}", exc)
            return None

        run_dir = Path("debug_images") / (
            datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:8]
        )
        run_dir.mkdir(parents=True, exist_ok=True)

        def _imwrite(path: Path, arr: "np.ndarray") -> None:
            if arr is None or getattr(arr, "size", 0) == 0:
                return
            cv2.imwrite(str(path), arr)

        # input/aligned là BGR từ OpenCV pipeline.
        _imwrite(run_dir / "01_input_bgr.png", image)
        _imwrite(run_dir / "02_aligned_bgr.png", aligned)

        cleaned_bgr = cleaned
        try:
            if cleaned.ndim == 3 and cleaned.shape[2] == 3:
                # Cleaner output expected RGB -> convert để lưu đúng màu bằng cv2.
                cleaned_bgr = cv2.cvtColor(cleaned, cv2.COLOR_RGB2BGR)
        except Exception:
            cleaned_bgr = cleaned

        _imwrite(run_dir / "03_cleaned.png", cleaned_bgr)

        annotated = cleaned_bgr.copy()
        for idx, box in enumerate(boxes):
            xmin = int(getattr(box, "xmin", 0))
            ymin = int(getattr(box, "ymin", 0))
            xmax = int(getattr(box, "xmax", 0))
            ymax = int(getattr(box, "ymax", 0))
            conf = float(getattr(box, "confidence", 0.0))
            cv2.rectangle(annotated, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
            cv2.putText(
                annotated,
                f"{idx}:{conf:.2f}",
                (xmin, max(0, ymin - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 200, 255),
                1,
                cv2.LINE_AA,
            )
        _imwrite(run_dir / "04_detector_boxes.png", annotated)

        # Lưu metadata text + output để tiện eyeball.
        metadata = {
            "lines": [
                {
                    "text": getattr(line, "text", ""),
                    "recognizer_confidence": float(
                        getattr(line, "recognizer_confidence", 0.0)
                    ),
                    "bbox": {
                        "xmin": int(getattr(getattr(line, "bbox", None), "xmin", 0)),
                        "ymin": int(getattr(getattr(line, "bbox", None), "ymin", 0)),
                        "xmax": int(getattr(getattr(line, "bbox", None), "xmax", 0)),
                        "ymax": int(getattr(getattr(line, "bbox", None), "ymax", 0)),
                    },
                }
                for line in lines
            ],
            "result": response.model_dump(),
        }

        import json

        with open(run_dir / "05_result.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info("OCR debug artifacts saved to {}", run_dir)
        return str(run_dir)


def _normalize_confidences(
    confidences: dict[str, float], data: CCCDData
) -> dict[str, float]:
    """Clamp confidence values and keep only fields present in the response."""
    normalized: dict[str, float] = {}
    for field_name, value in data.model_dump().items():
        if value is None:
            continue
        try:
            confidence = float(confidences.get(field_name, 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        normalized[field_name] = max(0.0, min(1.0, confidence))
    return normalized


__all__ = ["OCRPipeline", "PipelineTrace"]
