"""Recognizer – stage ④ của pipeline.

- `MockRecognizer`: gán text cố định cho từng box theo index.
- `RealTextRecognizer`: VietOCR (vgg_transformer / vgg_seq2seq) – nhận dạng
  text tiếng Việt cho từng bbox.

Lưu ý:
- Lần đầu khởi tạo Predictor sẽ download weights (~150MB transformer / ~50MB
  seq2seq) từ `https://vocr.vn/data/vietocr/{model}.pth`.
- Predictor cache qua `lru_cache`, share weight giữa các request.
- Input image expected RGB uint8 numpy: ảnh màu đã căn (pipeline đổi BGR -> RGB),
  không phải output của `RealImageCleaner`.
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


_SOS_TOKEN, _EOS_TOKEN, _MAX_SEQ_LENGTH = 1, 2, 128


def _decode_transformer_batch(
    predictor: Any, crops: list[Any]
) -> tuple[list[str], list[float], list[tuple[float, ...] | None]]:
    """Greedy decode mọi dòng trong 1 vòng: chữ trùng khớp `predict_batch` của VietOCR, nhanh ~3.5x.

    `predict_batch` gốc chia lô theo đúng bề rộng ảnh (~15 lô/thẻ) và chạy vòng giải mã riêng cho
    từng lô; mỗi bước decoder tốn ~18ms chủ yếu do chi phí khởi chạy kernel CUDA trên Windows.
    Ở đây CNN+encoder vẫn chạy theo lô bề rộng như gốc (đệm ảnh làm đổi kết quả), rồi gộp memory
    của mọi dòng, đệm và che phần đệm bằng `memory_key_padding_mask` để decode chung.
    Mỗi bước chỉ chạy decoder cho dòng chưa gặp EOS: một dòng nhiễu sinh chữ lặp tới giới hạn 128 ký tự
    từng kéo cả lô 94 dòng theo (ảnh trang A4 thật: nhận dạng 34s).
    Xác suất dòng = trung bình xác suất các ký tự trước EOS (gốc tính lẫn ký tự sinh sau EOS);
    trả kèm xác suất từng ký tự (None nếu không khớp được độ dài chữ).
    """
    import math
    from collections import defaultdict

    import torch
    import torch.nn.functional as F
    from vietocr.tool.translate import process_input  # type: ignore[import-untyped]

    dataset = predictor.config["dataset"]
    model, device = predictor.model, predictor.device
    seq = model.transformer
    tensors = [
        process_input(c, dataset["image_height"], dataset["image_min_width"], dataset["image_max_width"])
        for c in crops
    ]
    by_width: dict[int, list[int]] = defaultdict(list)
    for idx, tensor in enumerate(tensors):
        by_width[tensor.shape[-1]].append(idx)

    model.eval()
    with torch.no_grad():
        memories, order = [], []
        for indices in by_width.values():
            batch = torch.cat([tensors[i] for i in indices]).to(device)
            memories.append(seq.forward_encoder(model.cnn(batch)))  # S x n x E
            order.extend(indices)
        src_len = max(m.shape[0] for m in memories)
        memory = torch.cat([F.pad(m, (0, 0, 0, 0, 0, src_len - m.shape[0])) for m in memories], dim=1)
        positions = torch.arange(src_len, device=device)
        padding_mask = torch.cat([(positions >= m.shape[0]).expand(m.shape[1], src_len) for m in memories])

        count = len(order)
        tokens = torch.full((1, count), _SOS_TOKEN, dtype=torch.long, device=device)
        char_probs = [torch.ones(count, device=device)]
        finished = torch.zeros(count, dtype=torch.bool, device=device)
        steps = 0
        while steps <= _MAX_SEQ_LENGTH and not bool(finished.all()):
            active = (~finished).nonzero(as_tuple=True)[0]
            length = tokens.shape[0]
            causal = torch.triu(torch.full((length, length), float("-inf"), device=device), diagonal=1)
            target = seq.pos_enc(seq.embed_tgt(tokens[:, active]) * math.sqrt(seq.d_model))
            hidden = seq.transformer.decoder(
                target, memory[:, active], tgt_mask=causal, memory_key_padding_mask=padding_mask[active]
            )
            active_prob, active_token = F.softmax(seq.fc(hidden[-1]), dim=-1).max(dim=-1)
            # Dòng đã xong nhận EOS + xác suất 0: chữ giải mã dừng ở EOS đầu tiên nên không đổi.
            char_probs.append(active_prob.new_zeros(count).index_copy_(0, active, active_prob))
            token = active_token.new_full((count,), _EOS_TOKEN).index_copy_(0, active, active_token)
            tokens = torch.cat([tokens, token[None]])
            finished |= token == _EOS_TOKEN
            steps += 1

    sentences = tokens.T.cpu()
    probs = torch.stack(char_probs).T.cpu() * (sentences > 3)
    line_probs = (probs.sum(-1) / (probs > 0).sum(-1).clamp(min=1)).tolist()
    texts, out_probs = [""] * count, [0.0] * count
    out_chars: list[tuple[float, ...] | None] = [None] * count
    for row, (position, text) in enumerate(zip(order, predictor.vocab.batch_decode(sentences.tolist()))):
        ids = sentences[row].tolist()
        end = ids.index(_EOS_TOKEN) if _EOS_TOKEN in ids else len(ids)
        chars = probs[row, 1:end].tolist()
        texts[position], out_probs[position] = text, line_probs[row]
        out_chars[position] = tuple(chars) if len(chars) == len(text) else None
    return texts, out_probs, out_chars


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
      beamsearch: True → accuracy cao hơn, chậm hơn ~2x (chỉ áp dụng chế độ per-box).
      batch:      True → nhận dạng cả batch box trong 1 lần gọi `predict_batch`
                  (giảm latency). `predict_batch` của VietOCR luôn dùng greedy
                  decoding (bỏ qua beamsearch) nhưng trả confidence thật cho mỗi
                  dòng — khác `predict()` beamsearch (prob=None → không có confidence).
    """

    def __init__(
        self,
        *,
        model_name: str = "vgg_transformer",
        device: str = "auto",
        beamsearch: bool = True,
        batch: bool = True,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.beamsearch = beamsearch
        self.batch = batch
        if self.batch and self.beamsearch:
            logger.info(
                "RealTextRecognizer: batch=True nên bỏ qua beamsearch "
                "(VietOCR predict_batch chỉ hỗ trợ greedy decoding)."
            )
        # Pre-warm predictor (download weights nếu chưa có).
        _load_vietocr_predictor(self.model_name, self.device, self.beamsearch)
        logger.info(
            "RealTextRecognizer ready | model={} | device={} | beamsearch={} | batch={}",
            self.model_name, self.device, self.beamsearch, self.batch,
        )

    def recognize(
        self, image: "np.ndarray", boxes: list[BBox]
    ) -> list[TextLine]:
        if image is None or getattr(image, "size", 0) == 0:
            raise OCRStageError("recognizer", "Ảnh đầu vào rỗng.")
        if not boxes:
            return []

        predictor = _load_vietocr_predictor(
            self.model_name, self.device, self.beamsearch
        )

        # Crop tất cả box hợp lệ trước (giữ song song crop ↔ box).
        crops, kept_boxes = self._crop_boxes(image, boxes)
        if not crops:
            return []

        lines: list[TextLine] | None = None
        if self.batch and len(crops) > 1:
            lines = self._recognize_batch(predictor, crops, kept_boxes)
            if lines is None:
                logger.warning("predict_batch lỗi → fallback nhận dạng per-box.")
        if lines is None:
            lines = self._recognize_each(predictor, crops, kept_boxes)

        logger.debug(
            "RealTextRecognizer.recognize done | input_boxes={} | crops={} | lines={} | batch={}",
            len(boxes), len(crops), len(lines), self.batch,
        )
        return lines

    # ── internals ─────────────────────────────────────────────────────────

    def _crop_boxes(
        self, image: "np.ndarray", boxes: list[BBox]
    ) -> tuple[list[Any], list[BBox]]:
        """Crop từng box → PIL.Image, bỏ box thoái hoá. Trả crop list + box list song song."""
        from PIL import Image  # type: ignore[import-untyped]

        crops: list[Any] = []
        kept: list[BBox] = []
        for idx, box in enumerate(boxes):
            crop = self._safe_crop(image, box)
            if crop is None:
                logger.warning("Recognizer skip box[{}]: crop rỗng ({})", idx, box)
                continue
            crops.append(Image.fromarray(crop))
            kept.append(box)
        return crops, kept

    def _recognize_batch(
        self, predictor: Any, crops: list[Any], boxes: list[BBox]
    ) -> list[TextLine] | None:
        """Nhận dạng cả batch trong 1 lần gọi. Trả None nếu lỗi (để caller fallback)."""
        try:
            if getattr(predictor, "config", {}).get("seq_modeling") == "transformer":
                texts, probs, chars = _decode_transformer_batch(predictor, crops)
            else:
                texts, probs = predictor.predict_batch(crops, return_prob=True)
                chars = [None] * len(texts)
        except Exception as exc:  # noqa: BLE001 – fallback per-box ở caller.
            logger.warning("VietOCR predict_batch fail: {}", exc)
            return None
        lines = []
        for text, prob, char_probs, box in zip(texts, probs, chars, boxes):
            raw = str(text)
            stripped = raw.strip()
            lead = len(raw) - len(raw.lstrip())
            lines.append(
                TextLine(
                    text=stripped,
                    bbox=box,
                    recognizer_confidence=_safe_prob(prob),
                    char_confidences=None if char_probs is None else char_probs[lead : lead + len(stripped)],
                )
            )
        return lines

    def _recognize_each(
        self, predictor: Any, crops: list[Any], boxes: list[BBox]
    ) -> list[TextLine]:
        """Nhận dạng từng box (tôn trọng beamsearch). 1 box lỗi không kill request."""
        lines: list[TextLine] = []
        for idx, (crop, box) in enumerate(zip(crops, boxes)):
            try:
                text, prob = predictor.predict(crop, return_prob=True)
            except Exception as exc:  # noqa: BLE001 – per-box failure không kill request.
                logger.warning("Recognizer fail box[{}] {}: {}", idx, box, exc)
                continue
            lines.append(
                TextLine(
                    text=str(text).strip(),
                    bbox=box,
                    recognizer_confidence=_safe_prob(prob),
                )
            )
        return lines

    @staticmethod
    def _safe_crop(image: "np.ndarray", box: BBox) -> "np.ndarray | None":
        """Crop image theo bbox, clamp về bounds + skip degenerate."""
        h, w = image.shape[:2] if image.ndim >= 2 else (0, 0)
        if h == 0 or w == 0:
            return None
        if box.quad is not None:
            rotated = _straighten(image, box.quad)
            if rotated is not None:
                return rotated
        x1 = max(0, min(box.xmin, w - 1))
        y1 = max(0, min(box.ymin, h - 1))
        x2 = max(x1 + 1, min(box.xmax, w))
        y2 = max(y1 + 1, min(box.ymax, h))
        crop = image[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
            return None
        return crop


def _straighten(image: "np.ndarray", quad: tuple[tuple[float, float], ...]) -> "np.ndarray | None":
    """Nắn dòng chữ nghiêng về nằm ngang (như CropByPolys của PaddleOCR); None nếu tứ giác suy biến."""
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    src = np.float32(quad)
    width = int(max(np.linalg.norm(src[0] - src[1]), np.linalg.norm(src[2] - src[3])))
    height = int(max(np.linalg.norm(src[0] - src[3]), np.linalg.norm(src[1] - src[2])))
    if width < 2 or height < 2:
        return None
    dst = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(
        image, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def _safe_prob(prob: Any) -> float | None:
    """Chuẩn hoá prob từ VietOCR về confidence [0,1].

    `predict()` ở chế độ beamsearch trả prob=None → giữ None (không biết), để extractor
    không coi cả dòng là sai. `predict_batch`/greedy trả 1 scalar mỗi dòng (mean char prob).
    """
    if prob is None:
        return None
    try:
        return max(0.0, min(1.0, float(prob)))
    except (TypeError, ValueError):
        return None


__all__ = ["MockRecognizer", "RealTextRecognizer"]
