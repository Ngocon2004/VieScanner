from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("vietocr")

from PIL import Image  # noqa: E402
from vietocr.model.transformerocr import VietOCR  # noqa: E402
from vietocr.model.vocab import Vocab  # noqa: E402
from vietocr.tool.predictor import Predictor  # noqa: E402

from app.services.ocr.stages.recognizer import _decode_transformer_batch  # noqa: E402

VOCAB = "aAàÀbBcCdDđĐeEêÊ0123456789 ,./-"


def _tiny_predictor() -> SimpleNamespace:
    torch.manual_seed(0)
    vocab = Vocab(VOCAB)
    model = VietOCR(
        len(vocab),
        "vgg11_bn",
        {"ss": [[2, 2], [2, 2], [2, 1], [2, 1], [1, 1]], "ks": [[2, 2], [2, 2], [2, 1], [2, 1], [1, 1]],
         "hidden": 32, "pretrained": False},
        {"d_model": 32, "nhead": 2, "num_encoder_layers": 1, "num_decoder_layers": 2,
         "dim_feedforward": 64, "max_seq_length": 256, "pos_dropout": 0.0, "trans_dropout": 0.0},
        "transformer",
    ).eval()
    config = {"dataset": {"image_height": 32, "image_min_width": 32, "image_max_width": 160},
              "seq_modeling": "transformer"}
    return SimpleNamespace(config=config, model=model, device="cpu", vocab=vocab)


def test_single_loop_decode_matches_vietocr_predict_batch() -> None:
    predictor = _tiny_predictor()
    gen = torch.Generator().manual_seed(1)
    crops = [
        Image.fromarray((torch.rand(20, width, 3, generator=gen) * 255).byte().numpy())
        for width in (30, 55, 55, 90, 140, 200)
    ]
    expected, _ = Predictor.predict_batch(predictor, crops, return_prob=True)
    texts, probs, chars = _decode_transformer_batch(predictor, crops)
    assert texts == expected
    assert all(0.0 <= p <= 1.0 for p in probs)
    for text, prob, char_probs in zip(texts, probs, chars, strict=True):
        # Model ngẫu nhiên có thể sinh token đặc biệt giữa câu ("<pad>", "*"): không khớp được từng ký tự.
        if "<" in text or "*" in text:
            assert char_probs is None
            continue
        assert char_probs is not None and len(char_probs) == len(text)
        if text:
            assert abs(sum(char_probs) / len(char_probs) - prob) < 1e-5
