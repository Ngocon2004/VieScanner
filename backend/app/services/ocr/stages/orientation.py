"""Phân loại hướng thẻ đã căn (0/90/180/270 độ) bằng PaddleOCR PP-LCNet_x1_0_doc_ori (~11ms/ảnh CPU).

Pipeline chỉ gọi khi kết quả OCR kém: đo trên ảnh thật, chạy cho mọi ảnh làm xoay nhầm vài ảnh đang đọc tốt,
còn với ảnh đọc kém thì model chọn đúng hướng ở cả 2 ca xoay cứu được (1 -> 8 trường).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.core.logging import logger
from app.services.ocr.stages.detector import _to_paddle_device, ensure_cuda_libs_loaded

if TYPE_CHECKING:
    import numpy as np


@lru_cache(maxsize=2)
def _load_classifier(model_name: str, device: str) -> Any:
    ensure_cuda_libs_loaded()
    from paddleocr import DocImgOrientationClassification  # type: ignore[import-untyped]

    logger.info("Loading PaddleOCR DocImgOrientationClassification | model={} | device={}", model_name, device)
    return DocImgOrientationClassification(model_name=model_name, device=_to_paddle_device(device))


class RealOrientationClassifier:
    def __init__(self, *, model_name: str = "PP-LCNet_x1_0_doc_ori", device: str = "auto") -> None:
        self.model_name = model_name
        self.device = device
        _load_classifier(model_name, device)

    def predict(self, image: "np.ndarray") -> int:
        """Góc cần xoay ngược chiều kim đồng hồ để thẻ đứng thẳng (ảnh vào BGR)."""
        import cv2  # type: ignore[import-untyped]

        result = _load_classifier(self.model_name, self.device).predict(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        return int(result[0]["label_names"][0])


__all__ = ["RealOrientationClassifier"]
