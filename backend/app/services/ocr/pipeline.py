"""OCRPipeline – orchestrate 5 stage để biến ảnh -> CCCDData.

Pipeline nhận stage objects qua constructor (dependency injection), giúp:
  - Test: thay 1 stage bằng mock mà giữ nguyên các stage khác.
  - Production: thay MockX -> RealX (vd thay aligner mock -> YOLO aligner).
  - Hybrid: real cleaner + mock detector để debug từng stage.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import OCRFailedError
from app.core.logging import logger
from app.models.cccd import CCCDData, CCCDExtractResponse
from app.models.quality import QualityIssue, QualityReport
from app.services.ocr.address import fold
from app.services.ocr.card_geometry import card_region_from_headers
from app.services.ocr.cccd_number import decode_cccd_number
from app.services.ocr.interfaces import (
    Aligner,
    Cleaner,
    Detector,
    ExtractionResult,
    Extractor,
    OCRStageError,
    Recognizer,
)
from app.services.ocr.mrz import read_mrz
from app.services.ocr.placeholders import FIELD_PLACEHOLDERS
from app.services.ocr.qr import CCCDQRData, read_cccd_qr
from app.services.ocr.review import (
    POOR_MAX_FIELDS,
    fields_read,
    looks_like_back_side,
    residence_on_back,
    review_issues,
)
from app.utils.privacy import mask_id_number

if TYPE_CHECKING:
    import numpy as np


_UNEXPECTED_ERROR_MESSAGE = "Lỗi không mong muốn khi trích xuất ảnh này."
_TRUNCATED_CONFIDENCE = 0.5
# Thẻ cắt từ ảnh trang chỉ rộng ~330px: phóng to 2x đọc được họ tên, 3x không tốt hơn.
_CROP_TARGET_WIDTH = 800
_CROP_MAX_UPSCALE = 2.0
# Góc model hướng trả về -> hằng số cv2.rotate để dựng thẻ thẳng.
_ROTATE_CODES = {90: "ROTATE_90_COUNTERCLOCKWISE", 180: "ROTATE_180", 270: "ROTATE_90_CLOCKWISE"}


@dataclass(slots=True)
class PipelineTrace:
    """Trace metadata cho 1 lần chạy pipeline."""

    stage_ms: dict[str, float]
    total_ms: float
    num_boxes: int
    num_lines: int
    debug_dir: str | None = None


@dataclass(slots=True)
class _RunState:
    """Ảnh/kết quả trung gian, giữ lại để lưu debug kể cả khi một stage lỗi."""

    image: Any = None
    aligned: Any = None
    cleaned: Any = None
    boxes: list[Any] = field(default_factory=list)
    lines: list[Any] = field(default_factory=list)
    stage_ms: dict[str, float] = field(default_factory=dict)
    notices: list[QualityIssue] = field(default_factory=list)


def _decode_image(image_bytes: bytes) -> tuple["np.ndarray", "np.ndarray"]:
    """Decode bytes -> (ảnh gốc, ảnh đã resize) dạng BGR numpy (OpenCV format).

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

        stub = _StubImage(image_bytes)
        return stub, stub  # type: ignore[return-value]

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise OCRFailedError("Không thể decode ảnh đầu vào.")
    # Resize ảnh lớn để giảm latency/RAM của detector+recognizer.
    max_side = max(0, int(settings.ocr_max_image_side_px))
    h, w = img.shape[:2]
    longest = max(h, w)
    if max_side <= 0 or longest <= max_side:
        return img, img
    scale = max_side / float(longest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    logger.debug(
        "Resized OCR input from {}x{} -> {}x{} (max_side={})",
        w, h, new_w, new_h, max_side,
    )
    return img, resized


def _recognizer_input(aligned: Any, cleaned: Any) -> Any:
    # Recognizer đọc ảnh màu đã căn (BGR -> RGB): ảnh cleaned (nhị phân hóa) làm mất dấu tiếng Việt,
    # đo trên ảnh có QR làm đáp án: tỉ lệ từ đúng của họ tên 0.43 -> 0.88. Cleaned chỉ dùng cho detector;
    # hai ảnh cùng kích thước nên box của detector áp thẳng lên ảnh màu.
    if getattr(aligned, "ndim", 0) != 3 or aligned.shape[:2] != getattr(cleaned, "shape", ())[:2]:
        return cleaned
    import cv2  # type: ignore[import-untyped]

    return cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB)


def _result_score(result: ExtractionResult) -> tuple[int, bool]:
    return fields_read(result.confidences), decode_cccd_number(result.fields.get("id_number")) is not None


def _is_header(text: str) -> bool:
    folded = fold(text)
    return "conghoaxahoi" in folded or "cancuoc" in folded


def _is_poor(result: ExtractionResult) -> bool:
    read, id_valid = _result_score(result)
    return read <= POOR_MAX_FIELDS or not id_valid


def _read_qr(original: "np.ndarray", resized: "np.ndarray") -> CCCDQRData | None:
    qr_data = read_cccd_qr(resized)
    # QR nhỏ trên ảnh chụp xa có thể mất chi tiết sau resize: thử lại ở độ phân giải gốc.
    if qr_data is None and original is not resized:
        qr_data = read_cccd_qr(original)
    return qr_data


def _validated_cccd(result: ExtractionResult) -> CCCDData:
    """Dựng `CCCDData`; một trường sai chỉ hạ trường đó về placeholder, không làm hỏng cả kết quả.

    Ví dụ: địa chỉ ghép 2 dòng dài quá 200 ký tự, hay ngày OCR ra không hợp lệ, trước đây
    khiến cả ảnh trả `ocr_failed` dù các trường khác đọc đúng.
    """
    fields, confidences = result.fields, result.confidences
    for _ in range(len(fields) + 1):
        try:
            return CCCDData(**fields)
        except ValidationError as exc:
            for error in exc.errors():
                name = str(error["loc"][0]) if error.get("loc") else ""
                if error["type"] == "string_too_long" and name in fields:
                    max_length = int(error.get("ctx", {}).get("max_length", 0))
                    fields[name] = str(fields[name])[:max_length].rstrip(" ,")
                    confidences[name] = min(confidences.get(name, 0.0), _TRUNCATED_CONFIDENCE)
                elif name in FIELD_PLACEHOLDERS:
                    fields[name] = FIELD_PLACEHOLDERS[name]
                    confidences[name] = 0.0
                elif name == "expiry_date":
                    fields.pop(name, None)
                    confidences.pop(name, None)
                else:
                    raise
            logger.warning(
                "OCR field(s) không hợp lệ -> dùng placeholder: {}",
                sorted({str(e["loc"][0]) for e in exc.errors() if e.get("loc")}),
            )
    return CCCDData(**fields)


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
        orientation: Any | None = None,
    ) -> None:
        self._aligner = aligner
        self._cleaner = cleaner
        self._detector = detector
        self._recognizer = recognizer
        self._extractor = extractor
        self._orientation = orientation

    async def run(self, image_bytes: bytes) -> CCCDExtractResponse:
        """Async wrapper – sử dụng thread pool để không block event loop."""
        response, _trace = await asyncio.to_thread(self._run_sync, image_bytes)
        return response

    async def run_with_trace(self, image_bytes: bytes) -> tuple[CCCDExtractResponse, PipelineTrace]:
        """Chạy pipeline (non-blocking) và trả thêm trace timings/debug info."""
        return await asyncio.to_thread(self._run_sync, image_bytes)

    def _run_sync(self, image_bytes: bytes) -> tuple[CCCDExtractResponse, PipelineTrace]:
        state = _RunState()
        try:
            return self._run_stages(image_bytes, state)
        except OCRStageError as exc:
            logger.warning("Pipeline stage failed: {}", exc)
            self._save_failure_artifacts(state, exc.message)
            raise OCRFailedError(exc.message, code=f"ocr_{exc.stage}_failed") from exc
        except OCRFailedError as exc:
            self._save_failure_artifacts(state, exc.message)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline crashed unexpectedly")
            self._save_failure_artifacts(state, repr(exc))
            raise OCRFailedError(_UNEXPECTED_ERROR_MESSAGE, code="ocr_engine_crashed") from exc

    def _timed(self, state: _RunState, stage: str, fn: Any, *args: Any) -> Any:
        t0 = perf_counter()
        out = fn(*args)
        state.stage_ms[stage] = (perf_counter() - t0) * 1000
        return out

    def _run_stages(
        self, image_bytes: bytes, state: _RunState
    ) -> tuple[CCCDExtractResponse, PipelineTrace]:
        total_start = perf_counter()
        original, state.image = self._timed(state, "decode", _decode_image, image_bytes)
        state.aligned = state.cleaned = state.image
        logger.debug(
            "OCRPipeline start | bytes={} | shape={}",
            len(image_bytes),
            getattr(state.image, "shape", None),
        )

        # Đọc QR (CCCD gắn chip, Căn cước 2024) trước khi OCR. Không phụ thuộc OCR engine
        # nên hoạt động cả ở mock lẫn real engine.
        qr_data: CCCDQRData | None = None
        if settings.ocr_qr_enabled:
            qr_data = self._timed(state, "qr", _read_qr, original, state.image)
            if qr_data is not None:
                logger.info(
                    "QR CCCD detected | id_number={} | fields={}",
                    mask_id_number(qr_data.id_number),
                    sorted(qr_data.to_field_overrides()),
                )

        try:
            state.aligned = self._timed(state, "align", self._aligner.align, state.image)
            state.cleaned = self._timed(state, "clean", self._cleaner.clean, state.aligned)
            state.boxes = self._timed(state, "detect", self._detector.detect, state.cleaned)
            if not state.boxes:
                logger.warning("Detector trả về 0 box.")
                raise OCRFailedError(
                    "Không phát hiện được vùng văn bản nào.", code="ocr_detector_failed"
                )
            state.lines = self._timed(
                state,
                "recognize",
                self._recognizer.recognize,
                _recognizer_input(state.aligned, state.cleaned),
                state.boxes,
            )
            result = self._timed(state, "extract", self._extractor.extract, state.lines)
            result = self._retry_rotated(state, result)
            result = self._retry_card_crop(state, result)
        except (OCRStageError, OCRFailedError):
            # Không đọc được QR -> để lỗi OCR propagate như cũ.
            if qr_data is None:
                raise
            # Có QR -> QR là nguồn chính: trả dữ liệu QR-only, các trường QR
            # không cung cấp để placeholder (confidence 0) cho user rà soát.
            logger.warning("OCR thất bại nhưng đọc được QR -> trả dữ liệu QR-only.")
            result = ExtractionResult(fields=qr_data.to_full_fields(), confidences={})

        # QR (nếu có) ghi đè các trường nó cung cấp với confidence tuyệt đối;
        # các trường QR không có (quốc tịch, quê quán, hạn) giữ nguyên từ OCR.
        if qr_data is not None:
            overrides = qr_data.to_field_overrides()
            result.fields.update(overrides)
            for field_name in overrides:
                result.confidences[field_name] = 1.0

        back_side = looks_like_back_side(state.lines, result.confidences)
        if back_side:
            # Mặt sau không in ngày sinh: ngày extractor bắt được là ngày cấp (sai cả 4/4 ảnh đối chiếu với MRZ).
            result.fields.pop("dob", None)
            result.confidences.pop("dob", None)
        mrz_read = self._apply_mrz(state, result, back_side=back_side)

        cccd = _validated_cccd(result)
        response = CCCDExtractResponse(
            data=cccd,
            confidences=_normalize_confidences(result.confidences, cccd),
        )
        issues = state.notices + review_issues(
            response.confidences,
            back_side=back_side,
            mrz_read=mrz_read,
            residence_on_back=residence_on_back(state.lines, response.confidences),
        )
        if issues:
            response.quality = QualityReport(accepted=True, issues=issues)

        stage_ms = {k: round(v, 2) for k, v in state.stage_ms.items()}
        bottleneck = max(stage_ms, key=stage_ms.get)
        trace = PipelineTrace(
            stage_ms=stage_ms,
            total_ms=round((perf_counter() - total_start) * 1000, 2),
            num_boxes=len(state.boxes),
            num_lines=len(state.lines),
        )
        if settings.ocr_debug_save:
            trace.debug_dir = self._save_debug_artifacts(state, result=response.model_dump())

        logger.info(
            "OCRPipeline success | id_number={} | total_ms={} | stage_ms={} | bottleneck={}={}ms",
            mask_id_number(cccd.id_number),
            trace.total_ms,
            trace.stage_ms,
            bottleneck,
            trace.stage_ms[bottleneck],
        )
        return response, trace

    def _apply_mrz(self, state: _RunState, result: ExtractionResult, *, back_side: bool) -> bool:
        """Trường MRZ đã qua checksum ghi đè kết quả OCR theo nhãn, như QR ở mặt trước.

        Ảnh đã có họ tên (mặt sau thẻ Căn cước 2024 có QR, hoặc ảnh chụp cả 2 mặt): chỉ dùng khi số CCCD
        trong MRZ trùng số đã đọc (cùng một thẻ), và không ghi đè trường đã lấy từ QR.
        """
        mrz = self._timed(state, "mrz", read_mrz, [line.text for line in state.lines])
        if mrz is None:
            return False
        fields = mrz.to_fields()
        if not back_side:
            if mrz.id_number is None or mrz.id_number != result.fields.get("id_number"):
                return False
            fields = {name: value for name, value in fields.items() if result.confidences.get(name, 0) < 1.0}
        result.fields.update(fields)
        for name in fields:
            result.confidences[name] = 1.0
        logger.info("MRZ | back_side={} | id_number={} | fields={}", back_side, mask_id_number(mrz.id_number), sorted(fields))
        return True

    def _retry_rotated(self, state: _RunState, result: ExtractionResult) -> ExtractionResult:
        """Kết quả kém (không phải mặt sau): hỏi model hướng, xoay thẻ và OCR lại, giữ kết quả tốt hơn.

        Thẻ dọc/ngược sau khi căn làm OCR ra rác (1/8 trường); xoay đúng hướng đọc lại đủ 8 trường.
        """
        if (
            self._orientation is None
            or not _is_poor(result)
            or looks_like_back_side(state.lines, result.confidences)
        ):
            return result
        angle = self._timed(state, "orient", self._orientation.predict, state.aligned)
        if angle not in _ROTATE_CODES:
            return result
        import cv2  # type: ignore[import-untyped]

        started = perf_counter()
        try:
            rotated = cv2.rotate(state.aligned, getattr(cv2, _ROTATE_CODES[angle]))
            cleaned = self._cleaner.clean(rotated)
            boxes = self._detector.detect(cleaned)
            lines = self._recognizer.recognize(_recognizer_input(rotated, cleaned), boxes) if boxes else []
            retry = self._extractor.extract(lines)
        except OCRStageError as exc:
            logger.warning("OCR lại sau khi xoay {} độ lỗi, giữ kết quả cũ: {}", angle, exc)
            return result
        finally:
            state.stage_ms["rotate_retry"] = (perf_counter() - started) * 1000
        if _result_score(retry) <= _result_score(result):
            return result
        logger.info(
            "Xoay {} độ cải thiện kết quả | fields {} -> {}",
            angle, fields_read(result.confidences), fields_read(retry.confidences),
        )
        state.aligned, state.cleaned, state.boxes, state.lines = rotated, cleaned, boxes, lines
        return retry

    def _retry_card_crop(self, state: _RunState, result: ExtractionResult) -> ExtractionResult:
        """Thẻ chỉ chiếm một phần ảnh (bản photo/biểu mẫu): cắt vùng thẻ theo dòng tiêu đề, phóng to, OCR lại.

        Căn cả trang làm thứ tự dòng của các khối lẫn vào nhau và chữ thẻ quá nhỏ, nên mất họ tên/địa chỉ.
        Đo trên 6 ảnh trang thật: họ tên đọc được ở 5 ảnh trước đó mất tên.
        """
        if looks_like_back_side(state.lines, result.confidences):
            return result
        headers = [line.bbox for line in state.lines if _is_header(line.text)]
        region = card_region_from_headers(headers, state.aligned.shape)
        # Trang nhiều thẻ: kết quả cả trang có thể trộn trường của nhiều người -> luôn đọc riêng thẻ đầu.
        if region is None or (result.confidences.get("full_name", 0) > 0 and region.cards_on_page == 1):
            return result
        import cv2  # type: ignore[import-untyped]

        x0, y0, x1, y1 = region.box
        crop = state.aligned[y0:y1, x0:x1]
        scale = min(_CROP_MAX_UPSCALE, max(1.0, _CROP_TARGET_WIDTH / crop.shape[1]))
        if scale > 1:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        started = perf_counter()
        try:
            cleaned = self._cleaner.clean(crop)
            boxes = self._detector.detect(cleaned)
            lines = self._recognizer.recognize(_recognizer_input(crop, cleaned), boxes) if boxes else []
            retry = self._extractor.extract(lines)
        except OCRStageError as exc:
            logger.warning("OCR vùng thẻ cắt theo tiêu đề lỗi, giữ kết quả cũ: {}", exc)
            return result
        finally:
            state.stage_ms["card_crop_retry"] = (perf_counter() - started) * 1000
        if retry.confidences.get("full_name", 0) <= 0 or decode_cccd_number(retry.fields.get("id_number")) is None:
            return result
        # Chỉ bù trường từ kết quả cả trang khi cùng số CCCD: trang có thể chứa thẻ của người khác.
        if retry.fields["id_number"] == result.fields.get("id_number"):
            for name, conf in result.confidences.items():
                if conf > 0 and retry.confidences.get(name, 0) <= 0:
                    retry.fields[name], retry.confidences[name] = result.fields[name], conf
        logger.info(
            "Cắt vùng thẻ theo tiêu đề | cards_on_page={} | fields {} -> {}",
            region.cards_on_page, fields_read(result.confidences), fields_read(retry.confidences),
        )
        if region.cards_on_page > 1:
            state.notices.append(
                QualityIssue(
                    code="multiple_cards",
                    severity="soft",
                    message=f"Ảnh có {region.cards_on_page} thẻ, hệ thống chỉ đọc thẻ đầu tiên. Hãy tải riêng từng thẻ.",
                    metric=float(region.cards_on_page),
                )
            )
        state.aligned, state.cleaned, state.boxes, state.lines = crop, cleaned, boxes, lines
        return retry

    def _save_failure_artifacts(self, state: _RunState, error: str) -> None:
        # Ảnh trung gian của lần chạy lỗi mới là thứ cần nhất khi debug (vd 02_aligned khi aligner lỗi).
        if settings.ocr_debug_save and state.image is not None:
            self._save_debug_artifacts(state, error=error)

    def _save_debug_artifacts(
        self,
        state: _RunState,
        *,
        result: dict | None = None,
        error: str | None = None,
    ) -> str | None:
        """Lưu ảnh trung gian + annotation để debug OCR."""
        try:
            import cv2  # type: ignore[import-untyped]
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR_DEBUG_SAVE=true nhưng import cv2 fail: {}", exc)
            return None

        try:
            run_dir = Path("debug_images") / (
                datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid4().hex[:8]
            )
            run_dir.mkdir(parents=True, exist_ok=True)

            def _imwrite(path: Path, arr: Any) -> None:
                if arr is None or getattr(arr, "size", 0) == 0:
                    return
                cv2.imwrite(str(path), arr)

            # input/aligned là BGR từ OpenCV pipeline.
            _imwrite(run_dir / "01_input_bgr.png", state.image)
            if state.aligned is not state.image:
                _imwrite(run_dir / "02_aligned_bgr.png", state.aligned)

            if state.cleaned is not state.aligned and state.cleaned is not None:
                cleaned_bgr = state.cleaned
                if getattr(cleaned_bgr, "ndim", 0) == 3 and cleaned_bgr.shape[2] == 3:
                    # Cleaner output expected RGB -> convert để lưu đúng màu bằng cv2.
                    cleaned_bgr = cv2.cvtColor(cleaned_bgr, cv2.COLOR_RGB2BGR)
                _imwrite(run_dir / "03_cleaned.png", cleaned_bgr)

                annotated = cleaned_bgr.copy()
                for idx, box in enumerate(state.boxes):
                    cv2.rectangle(annotated, (box.xmin, box.ymin), (box.xmax, box.ymax), (0, 255, 0), 2)
                    cv2.putText(
                        annotated,
                        f"{idx}:{box.confidence:.2f}",
                        (box.xmin, max(0, box.ymin - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        (0, 200, 255),
                        1,
                        cv2.LINE_AA,
                    )
                _imwrite(run_dir / "04_detector_boxes.png", annotated)

            metadata = {
                "stage_ms": {k: round(v, 2) for k, v in state.stage_ms.items()},
                "error": error,
                "lines": [
                    {
                        "text": line.text,
                        "recognizer_confidence": line.recognizer_confidence,
                        "bbox": {
                            "xmin": line.bbox.xmin,
                            "ymin": line.bbox.ymin,
                            "xmax": line.bbox.xmax,
                            "ymax": line.bbox.ymax,
                        },
                    }
                    for line in state.lines
                ],
                "result": result,
            }
            with open(run_dir / "05_result.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001 – lưu debug không được làm hỏng request.
            logger.warning("Không lưu được debug artifacts: {}", exc)
            return None

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
