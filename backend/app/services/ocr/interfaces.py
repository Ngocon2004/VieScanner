"""Interface (Protocol) cho các stage trong pipeline OCR.

Mỗi stage là một interface đơn giản nhận numpy array và trả về output mở rộng.
Tất cả implementation (mock/real) phải tuân thủ shape input/output này để
`OCRPipeline` có thể swap mà không cần đổi code.

Không import bất kỳ thư viện ML nào ở module này – chỉ Python stdlib + numpy
(nếu installed). Như vậy import scaffolding không kéo theo Torch/Paddle/v.v.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    # numpy chỉ là type hint; runtime engine mock không cần.
    import numpy as np

    ImageArray = np.ndarray
else:
    ImageArray = "np.ndarray"  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BBox:
    """Bounding box trục thẳng (axis-aligned), pixel toạ độ.

    `confidence` là điểm tin cậy từ detector (0-1); 1.0 nếu detector không cấp.
    """

    xmin: int
    ymin: int
    xmax: int
    ymax: int
    confidence: float = 1.0
    # 4 góc (trên-trái, trên-phải, dưới-phải, dưới-trái) của dòng chữ nghiêng: recognizer cắt xoay theo
    # tứ giác này thay vì hình chữ nhật thẳng (lẫn chữ dòng bên cạnh). None = cắt thẳng.
    quad: tuple[tuple[float, float], ...] | None = None

    @property
    def width(self) -> int:
        return self.xmax - self.xmin

    @property
    def height(self) -> int:
        return self.ymax - self.ymin

    @property
    def center_y(self) -> int:
        return (self.ymin + self.ymax) // 2


@dataclass(frozen=True, slots=True)
class TextLine:
    """Một dòng text recognize được, gắn với bbox + confidence."""

    text: str
    bbox: BBox
    # None = recognizer không cung cấp xác suất (VietOCR beamsearch), KHÁC với 0 = chắc chắn sai.
    recognizer_confidence: float | None = 1.0
    # Xác suất từng ký tự, cùng độ dài với `text`. Trung bình cả dòng che mất 1 chữ đọc sai dấu
    # ("Đinh" -> "Đỉnh" vẫn ~0.9); extractor dùng chữ yếu nhất để cảnh báo. None = không có.
    char_confidences: tuple[float, ...] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class OCRStageError(Exception):
    """Lỗi xảy ra trong một stage cụ thể của pipeline.

    `stage` là tên stage (aligner/cleaner/detector/...). Sẽ được map sang
    error code khi propagate lên FastAPI exception handler.
    """

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"[{stage}] {message}")
        self.stage = stage
        self.message = message


# ─────────────────────────────────────────────────────────────────────────────
# Stage protocols
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class Aligner(Protocol):
    """Stage ①: căn chỉnh & crop ảnh CCCD từ ảnh đầu vào bất kỳ."""

    def align(self, image: ImageArray) -> ImageArray:
        """Trả về ảnh CCCD đã được warp về dạng thẳng (BGR uint8 numpy).

        Raise `OCRStageError("aligner", ...)` nếu không detect được 4 góc.
        """
        ...


@runtime_checkable
class Cleaner(Protocol):
    """Stage ②: làm sạch ảnh (shadow removal + contrast + denoise)."""

    def clean(self, image: ImageArray) -> ImageArray:
        """Trả về ảnh đã clean (RGB uint8 numpy, hợp với PaddleOCR input)."""
        ...


@runtime_checkable
class Detector(Protocol):
    """Stage ③: detect các vùng text trong ảnh."""

    def detect(self, image: ImageArray) -> list[BBox]:
        """Trả về list BBox cho các text region.

        Raise `OCRStageError("detector", ...)` nếu detector lỗi nội bộ.
        Không raise nếu không detect được box nào (return empty list).
        """
        ...


@runtime_checkable
class Recognizer(Protocol):
    """Stage ④: nhận dạng text trong từng bbox."""

    def recognize(
        self, image: ImageArray, boxes: list[BBox]
    ) -> list[TextLine]:
        """Trả về list TextLine theo đúng thứ tự `boxes`.

        Box và TextLine ở cùng index → caller có thể correlate.
        Raise `OCRStageError("recognizer", ...)` nếu lỗi inference.
        """
        ...


@runtime_checkable
class Extractor(Protocol):
    """Stage ⑤: trích xuất các trường có cấu trúc từ list TextLine."""

    def extract(self, lines: list[TextLine]) -> ExtractionResult:
        """Trả về `ExtractionResult` chứa CCCDData + confidence per field."""
        ...


@dataclass(slots=True)
class ExtractionResult:
    """Kết quả extraction: data + confidence per field.

    `confidences` map field name → 0-1. Có thể vắng key nếu không extract được.
    """

    # Dùng dict thay vì pydantic model ở đây để giảm coupling; pipeline sẽ
    # convert sang CCCDData ở tầng ngoài.
    fields: dict[str, str]
    confidences: dict[str, float]
