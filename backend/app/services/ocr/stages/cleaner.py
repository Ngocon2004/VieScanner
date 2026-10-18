"""Cleaner – stage ② của pipeline.

- `MockCleaner`: trả về ảnh gốc (dùng cho dev/test).
- `RealImageCleaner`: full OpenCV cleaning pipeline – shadow removal +
  auto contrast + smoothing. Port từ denghwee/OCR_Vietnamese_Read_CCCD với
  cải tiến nhỏ (bỏ no-op 1x1 dilate/erode).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import logger
from app.services.ocr.interfaces import OCRStageError

if TYPE_CHECKING:
    import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Mock
# ─────────────────────────────────────────────────────────────────────────────


class MockCleaner:
    """Trả về ảnh gốc, không clean gì."""

    def clean(self, image: "np.ndarray") -> "np.ndarray":
        logger.debug("MockCleaner.clean passthrough | shape={}", getattr(image, "shape", None))
        return image


# ─────────────────────────────────────────────────────────────────────────────
# Real – OpenCV pipeline
# ─────────────────────────────────────────────────────────────────────────────


def _odd_at_least(value: int, minimum: int) -> int:
    v = max(minimum, int(value))
    return v if v % 2 == 1 else v + 1


class RealImageCleaner:
    """Pipeline làm sạch ảnh CCCD trước khi đẩy vào text detector.

    Các bước (theo thứ tự):
      1. Chuyển grayscale (nếu chưa).
      2. Shadow removal: dilate(7×7) → medianBlur(21) tạo background → trừ.
      3. Smoothing: GaussianBlur(5×5).
      4. Auto contrast: histogram clipping 1%.
      5. Convert grayscale → RGB (để compat với PaddleOCR).

    Cho ảnh chụp CCCD bằng phone (có shadow + uneven lighting), bước 2-4 giúp
    detector ổn định hơn rất nhiều.
    """

    def __init__(
        self,
        *,
        shadow_kernel_size: int = 7,
        background_blur: int = 21,
        smooth_kernel_size: int = 5,
        clip_hist_percent: float = 1.0,
    ) -> None:
        # Kernel lấy từ env: số chẵn/<=0 làm OpenCV raise giữa request (medianBlur, GaussianBlur
        # chỉ nhận số lẻ) -> chuẩn hóa một lần ở đây.
        self.shadow_kernel_size = max(1, int(shadow_kernel_size))
        self.background_blur = _odd_at_least(background_blur, 3)
        self.smooth_kernel_size = _odd_at_least(smooth_kernel_size, 1)
        self.clip_hist_percent = max(0.0, min(50.0, float(clip_hist_percent)))

    def clean(self, image: "np.ndarray") -> "np.ndarray":
        import cv2  # type: ignore[import-untyped]
        import numpy as np

        if image is None or getattr(image, "size", 0) == 0:
            raise OCRStageError("cleaner", "Ảnh đầu vào rỗng.")

        cleaned = self._remove_shadow_and_enhance(image)

        # Convert grayscale → RGB (3 kênh) để compat với PaddleOCR input format.
        cleaned_rgb = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2RGB)
        logger.debug(
            "RealImageCleaner.clean done | in={} out={}",
            getattr(image, "shape", None),
            cleaned_rgb.shape,
        )
        return cleaned_rgb

    def _remove_shadow_and_enhance(self, image: "np.ndarray") -> "np.ndarray":
        import cv2
        import numpy as np

        # 1. Grayscale
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # 2. Shadow removal – tách background ra rồi trừ.
        kernel = np.ones(
            (self.shadow_kernel_size, self.shadow_kernel_size), np.uint8
        )
        dilated = cv2.dilate(gray, kernel)
        background = cv2.medianBlur(dilated, self.background_blur)
        diff = 255 - cv2.absdiff(gray, background)

        # 3. Smoothing.
        if self.smooth_kernel_size >= 3:
            diff = cv2.GaussianBlur(
                diff,
                (self.smooth_kernel_size, self.smooth_kernel_size),
                0,
            )

        # 4. Auto contrast.
        diff, _, _ = self._automatic_brightness_and_contrast(
            diff, clip_hist_percent=self.clip_hist_percent
        )
        return diff

    @staticmethod
    def _automatic_brightness_and_contrast(
        gray: "np.ndarray", clip_hist_percent: float = 1.0
    ) -> tuple["np.ndarray", float, float]:
        """Cân bằng sáng & tương phản dựa trên histogram clipping."""
        import cv2
        import numpy as np

        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        accumulator = np.cumsum(hist)
        maximum = float(accumulator[-1])

        clip = clip_hist_percent * (maximum / 100.0) / 2.0
        minimum_gray = int(np.searchsorted(accumulator, clip))
        maximum_gray = int(np.searchsorted(accumulator, maximum - clip))

        # Tránh chia 0 khi ảnh quá đều.
        spread = max(1, maximum_gray - minimum_gray)
        alpha = 255.0 / spread
        beta = -minimum_gray * alpha

        result = cv2.convertScaleAbs(gray, alpha=alpha, beta=beta)
        return result, alpha, beta


__all__ = ["MockCleaner", "RealImageCleaner"]
