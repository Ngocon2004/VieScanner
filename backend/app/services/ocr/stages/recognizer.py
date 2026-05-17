"""Recognizer – stage ④ của pipeline.

- `MockRecognizer`: gán text cố định cho từng box theo index.
- `RealTextRecognizer`: VietOCR (vgg_transformer / vgg_seq2seq) – nhận dạng
  text tiếng Việt cho từng bbox.

Lưu ý:
- Lần đầu khởi tạo Predictor sẽ download weights (~150MB transformer / ~50MB
  seq2seq) từ `https://vocr.vn/data/vietocr/{model}.pth`.
- Predictor cache qua `lru_cache`, share weight giữa các request.
- Input image expected RGB uint8 numpy (output của `RealImageCleaner`).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.core.logging import logger
from app.services.ocr.interfaces import BBox, OCRStageError, TextLine

if TYPE_CHECKING:
    import numpy as np


# Text mock theo thứ tự bbox của MockDetector (8 trường CCCD).
_MOCK_TEXTS: tuple[str, ...] = (
    "001202000123",
    "NGUYỄN VĂN A",
    "01/01/2002",
    "Nam",
    "Việt Nam",
    "Phường Bến Nghé, Quận 1, TP. Hồ Chí Minh",
    "123 Đường Lê Lợi, Quận 1, TP. Hồ Chí Minh",
    "01/01/2027",
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock
# ─────────────────────────────────────────────────────────────────────────────


class MockRecognizer:
    """Trả về text cố định cho từng box (theo index)."""

    def recognize(
        self, image: "np.ndarray", boxes: list[BBox]
    ) -> list[TextLine]:
        lines: list[TextLine] = []
        for idx, box in enumerate(boxes):
            text = _MOCK_TEXTS[idx] if idx < len(_MOCK_TEXTS) else f"[mock_{idx}]"
            lines.append(TextLine(text=text, bbox=box, recognizer_confidence=0.92))
        logger.debug("MockRecognizer.recognize | lines={}", len(lines))
        return lines


# ─────────────────────────────────────────────────────────────────────────────
# Real – VietOCR (vgg_transformer / vgg_seq2seq)
# ─────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=2)
def _load_vietocr_predictor(
    model_name: str, device: str, beamsearch: bool
) -> Any:
    """Load VietOCR Predictor 1 lần / process. Cache theo (model, device, beamsearch).

    Lần đầu chạy sẽ download weights (~150MB transformer / ~50MB seq2seq) từ
    https://vocr.vn vào ~/.cache/vietocr/.
    """
    # Import muộn để mock pipeline không phụ thuộc vietocr.
    from vietocr.tool.config import Cfg  # type: ignore[import-untyped]
    from vietocr.tool.predictor import Predictor  # type: ignore[import-untyped]

    config = Cfg.load_config_from_name(model_name)
    config["cnn"]["pretrained"] = True
    config["predictor"]["beamsearch"] = beamsearch
    config["device"] = _resolve_device(device)
    # Tắt log noise của vietocr nếu config có flag.
    if "quiet" in config:
        config["quiet"] = True

    logger.info(
        "Loading VietOCR Predictor | model={} | device={} | beamsearch={}",
        model_name, config["device"], beamsearch,
    )
    return Predictor(config)


def _resolve_device(device: str) -> str:
    """`auto` → 'cuda:0' nếu có CUDA, ngược lại 'cpu'. Tương tự aligner."""
    if device != "auto":
        return device
    try:
        import torch  # type: ignore[import-untyped]
    except ImportError:
        return "cpu"
    return "cuda:0" if torch.cuda.is_available() else "cpu"


class RealTextRecognizer:
    """Nhận dạng text từ ảnh + bbox bằng VietOCR.

    Args:
      model_name: 'vgg_transformer' (recommend) | 'vgg_seq2seq'.
      device:     'auto' | 'cpu' | 'cuda:0'.
      beamsearch: True → accuracy cao hơn, chậm hơn ~2x.
    """

    def __init__(
        self,
        *,
        model_name: str = "vgg_transformer",
        device: str = "auto",
        beamsearch: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.beamsearch = beamsearch
        # Pre-warm predictor (download weights nếu chưa có).
        _load_vietocr_predictor(self.model_name, self.device, self.beamsearch)
        logger.info(
            "RealTextRecognizer ready | model={} | device={} | beamsearch={}",
            self.model_name, self.device, self.beamsearch,
        )

    def recognize(
        self, image: "np.ndarray", boxes: list[BBox]
    ) -> list[TextLine]:
        if image is None or getattr(image, "size", 0) == 0:
            raise OCRStageError("recognizer", "Ảnh đầu vào rỗng.")
        if not boxes:
            return []

        from PIL import Image  # type: ignore[import-untyped]

        predictor = _load_vietocr_predictor(
            self.model_name, self.device, self.beamsearch
        )

        lines: list[TextLine] = []
        for idx, box in enumerate(boxes):
            crop = self._safe_crop(image, box)
            if crop is None:
                logger.warning(
                    "Recognizer skip box[{}]: crop rỗng ({})", idx, box
                )
                continue

            pil_img = Image.fromarray(crop)
            try:
                text, prob = predictor.predict(pil_img, return_prob=True)
            except Exception as exc:  # noqa: BLE001 – per-box failure không kill request.
                logger.warning(
                    "Recognizer fail box[{}] {}: {}", idx, box, exc
                )
                continue

            lines.append(
                TextLine(
                    text=str(text).strip(),
                    bbox=box,
                    recognizer_confidence=float(prob) if prob is not None else 0.0,
                )
            )

        logger.debug(
            "RealTextRecognizer.recognize done | input_boxes={} | lines={}",
            len(boxes), len(lines),
        )
        return lines

    @staticmethod
    def _safe_crop(image: "np.ndarray", box: BBox) -> "np.ndarray | None":
        """Crop image theo bbox, clamp về bounds + skip degenerate."""
        h, w = image.shape[:2] if image.ndim >= 2 else (0, 0)
        if h == 0 or w == 0:
            return None
        x1 = max(0, min(box.xmin, w - 1))
        y1 = max(0, min(box.ymin, h - 1))
        x2 = max(x1 + 1, min(box.xmax, w))
        y2 = max(y1 + 1, min(box.ymax, h))
        crop = image[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
            return None
        return crop


__all__ = ["MockRecognizer", "RealTextRecognizer"]
