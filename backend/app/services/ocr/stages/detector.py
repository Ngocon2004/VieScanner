"""Detector – stage ③ của pipeline.

- `MockDetector`: trả về list bbox cố định (8 box mô phỏng các vùng text trên CCCD).
- `RealTextDetector`: PaddleOCR `TextDetection` (PP-OCRv5_server_det / mobile_det).

PaddleOCR 3.x trả `dt_polys` dạng quadrilateral (4×2). Ta convert về axis-aligned
BBox để compatible với recognizer (cắt rectangle thay vì warp 4 điểm).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.core.logging import logger
from app.services.ocr.interfaces import BBox, OCRStageError

if TYPE_CHECKING:
    import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Mock
# ─────────────────────────────────────────────────────────────────────────────


class MockDetector:
    """Trả về 8 bbox mock theo layout CCCD chuẩn (proportional)."""

    def detect(self, image: "np.ndarray") -> list[BBox]:
        # Lấy kích thước thật nếu có numpy; fallback dùng tỉ lệ giả định 800x504.
        if hasattr(image, "shape") and len(image.shape) >= 2:
            h, w = image.shape[:2]
        else:
            h, w = 504, 800

        # 8 vùng tương ứng các trường CCCD theo layout 2020 (proportional).
        # Toạ độ theo tỉ lệ ảnh để mock không phụ thuộc kích thước.
        rel_boxes = [
            (0.32, 0.18, 0.65, 0.25),  # id_number
            (0.32, 0.28, 0.85, 0.36),  # full_name
            (0.32, 0.40, 0.55, 0.47),  # dob
            (0.32, 0.49, 0.50, 0.55),  # gender
            (0.60, 0.49, 0.85, 0.55),  # nationality
            (0.32, 0.58, 0.95, 0.66),  # origin
            (0.32, 0.68, 0.95, 0.78),  # residence
            (0.32, 0.84, 0.60, 0.91),  # expiry_date
        ]
        boxes = [
            BBox(
                xmin=int(rx1 * w),
                ymin=int(ry1 * h),
                xmax=int(rx2 * w),
                ymax=int(ry2 * h),
                confidence=0.95,
            )
            for rx1, ry1, rx2, ry2 in rel_boxes
        ]
        logger.debug("MockDetector.detect | image={}x{} | boxes={}", w, h, len(boxes))
        return boxes


# ─────────────────────────────────────────────────────────────────────────────
# Real – PaddleOCR PP-OCRv5_*_det
# ─────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=2)
def _load_paddle_detector(model_name: str, device: str) -> Any:
    """Load PaddleOCR TextDetection 1 lần / process. Cache theo (model, device).

    Lần đầu sẽ auto-download model (~5MB mobile / ~84MB server).
    """
    # Import muộn để mock pipeline không phụ thuộc paddle.
    from paddleocr import TextDetection  # type: ignore[import-untyped]

    logger.info(
        "Loading PaddleOCR TextDetection | model={} | device={}", model_name, device
    )
    # PaddleOCR API: device='cpu' | 'gpu' | 'gpu:0'. Không hỗ trợ 'cuda:0'.
    paddle_device = _to_paddle_device(device)
    return TextDetection(model_name=model_name, device=paddle_device)


def _to_paddle_device(device: str) -> str:
    """Map device chung của VieScanner → device string mà Paddle nhận."""
    d = device.lower()
    if d in ("auto",):
        # PaddleOCR sẽ tự chọn nếu không pass device. Ta vẫn explicit để rõ.
        try:
            import paddle  # type: ignore[import-untyped]
            return "gpu" if paddle.is_compiled_with_cuda() else "cpu"
        except ImportError:
            return "cpu"
    if d.startswith("cuda"):
        # cuda:0 → gpu:0; cuda → gpu
        idx = d.split(":", 1)[1] if ":" in d else None
        return f"gpu:{idx}" if idx is not None else "gpu"
    if d.startswith("gpu") or d == "cpu":
        return d
    # Fallback an toàn.
    return "cpu"


class RealTextDetector:
    """Detect bbox text bằng PaddleOCR PP-OCRv5_*_det.

    Output: `list[BBox]` axis-aligned, đã pad + sort top-to-bottom rồi left-to-right.
    Caller (Recognizer) sẽ crop từng bbox để OCR.

    Args:
      model_name: tên model PaddleOCR (xem `Settings.ocr_detector_model`).
      device:     'auto' | 'cpu' | 'cuda:0' | 'gpu' (auto-mapped sang Paddle format).
      conf_threshold: lọc bỏ box có confidence thấp hơn ngưỡng này.
      padding:    pixel pad mỗi side của bbox.
    """

    def __init__(
        self,
        *,
        model_name: str = "PP-OCRv5_server_det",
        device: str = "auto",
        conf_threshold: float = 0.30,
        padding: int = 4,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.conf_threshold = max(0.0, min(1.0, float(conf_threshold)))
        self.padding = max(0, padding)
        # Pre-warm để fail-fast nếu model không tải được + share weights.
        _load_paddle_detector(self.model_name, self.device)
        logger.info(
            "RealTextDetector ready | model={} | device={} | conf_threshold={} | padding={}",
            self.model_name,
            self.device,
            self.conf_threshold,
            self.padding,
        )

    def detect(self, image: "np.ndarray") -> list[BBox]:
        if image is None or getattr(image, "size", 0) == 0:
            raise OCRStageError("detector", "Ảnh đầu vào rỗng.")

        detector = _load_paddle_detector(self.model_name, self.device)
        try:
            results = detector.predict(input=image, batch_size=1)
        except Exception as exc:  # noqa: BLE001 – Paddle có thể fail nhiều lý do.
            raise OCRStageError(
                "detector", f"PaddleOCR inference lỗi: {exc}"
            ) from exc

        boxes = self._results_to_bboxes(results, image)
        logger.debug(
            "RealTextDetector.detect done | image={} | boxes={}",
            getattr(image, "shape", None), len(boxes),
        )
        return boxes

    # ── internals ─────────────────────────────────────────────────────────

    def _results_to_bboxes(
        self, results: Any, image: "np.ndarray"
    ) -> list[BBox]:
        """Chuyển PaddleOCR result list → list[BBox] axis-aligned + sorted."""
        import numpy as np

        # PaddleOCR predict() trả về iterable các "Result" object; chỉ có 1 phần
        # tử khi batch_size=1. Mỗi Result có .json["res"] chứa dt_polys + dt_scores.
        all_boxes: list[BBox] = []
        h, w = image.shape[:2] if image.ndim >= 2 else (0, 0)

        for res in results:
            res_dict = self._extract_res_dict(res)
            polys = res_dict.get("dt_polys")
            scores = res_dict.get("dt_scores") or []
            if polys is None or len(polys) == 0:
                continue
            polys_arr = np.asarray(polys)
            for idx, quad in enumerate(polys_arr):
                # quad: (4, 2) – 4 đỉnh quadrilateral
                xs = quad[:, 0]
                ys = quad[:, 1]
                xmin = int(max(0, xs.min() - self.padding))
                ymin = int(max(0, ys.min() - self.padding))
                xmax = int(min(w - 1 if w else xs.max() + self.padding,
                               xs.max() + self.padding))
                ymax = int(min(h - 1 if h else ys.max() + self.padding,
                               ys.max() + self.padding))
                # Bỏ box thoái hoá (xmin >= xmax hoặc ymin >= ymax sau khi pad/clamp).
                if xmax <= xmin or ymax <= ymin:
                    continue
                conf = float(scores[idx]) if idx < len(scores) else 1.0
                if conf < self.conf_threshold:
                    continue
                all_boxes.append(BBox(xmin, ymin, xmax, ymax, conf))

        # Sort top-to-bottom rồi left-to-right – thuận với reading order CCCD.
        # Group dòng bằng overlap y: 2 box cùng dòng nếu |center_y_a - center_y_b| < median_h*0.5.
        all_boxes.sort(key=lambda b: (b.center_y, b.xmin))
        return all_boxes

    @staticmethod
    def _extract_res_dict(res: Any) -> dict:
        """Lấy phần dữ liệu từ object result (PaddleOCR thay đổi shape qua các version).

        Hỗ trợ: `res.json["res"]`, `res.json` raw, hoặc dict-like.
        """
        # Cách phổ biến nhất ở 3.x
        json_obj = getattr(res, "json", None)
        if isinstance(json_obj, dict):
            if "res" in json_obj and isinstance(json_obj["res"], dict):
                return json_obj["res"]
            return json_obj
        if isinstance(res, dict):
            return res.get("res", res)
        # Fallback: best-effort
        return {}


__all__ = ["MockDetector", "RealTextDetector"]
