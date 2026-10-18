"""Unit tests cho RealTextRecognizer batch mode (L2).

Không load VietOCR thật: monkeypatch `_load_vietocr_predictor` trả về predictor
giả để kiểm tra logic dispatch batch/per-box + fallback + chuẩn hoá confidence.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from app.services.ocr.interfaces import BBox  # noqa: E402
from app.services.ocr.stages import recognizer as rec_mod  # noqa: E402


class FakePredictor:
    """Predictor giả: đếm số lần gọi để verify đường đi batch vs per-box."""

    def __init__(self) -> None:
        self.batch_calls = 0
        self.predict_calls = 0
        self.batch_raises = False

    def predict_batch(self, imgs, return_prob=False):  # noqa: ANN001
        self.batch_calls += 1
        if self.batch_raises:
            raise RuntimeError("predict_batch boom")
        texts = [f"line{i}" for i in range(len(imgs))]
        probs = [0.9] * len(imgs)
        return (texts, probs) if return_prob else texts

    def predict(self, img, return_prob=False):  # noqa: ANN001
        self.predict_calls += 1
        return ("perbox", 0.8) if return_prob else "perbox"


def _image(h: int = 120, w: int = 400):
    return np.full((h, w, 3), 200, dtype=np.uint8)


def _two_boxes() -> list[BBox]:
    return [BBox(10, 10, 120, 45, 0.9), BBox(10, 55, 240, 95, 0.9)]


@pytest.fixture
def patched_predictor(monkeypatch: pytest.MonkeyPatch) -> FakePredictor:
    fake = FakePredictor()
    monkeypatch.setattr(rec_mod, "_load_vietocr_predictor", lambda *a, **k: fake)
    return fake


def test_batch_mode_calls_predict_batch_once(patched_predictor: FakePredictor) -> None:
    recognizer = rec_mod.RealTextRecognizer(batch=True)
    lines = recognizer.recognize(_image(), _two_boxes())

    assert patched_predictor.batch_calls == 1
    assert patched_predictor.predict_calls == 0
    assert [line.text for line in lines] == ["line0", "line1"]
    # box ↔ line giữ đúng thứ tự + confidence chuẩn hoá.
    assert lines[0].bbox == _two_boxes()[0]
    assert all(line.recognizer_confidence == pytest.approx(0.9) for line in lines)


def test_batch_failure_falls_back_to_per_box(patched_predictor: FakePredictor) -> None:
    patched_predictor.batch_raises = True
    recognizer = rec_mod.RealTextRecognizer(batch=True)
    lines = recognizer.recognize(_image(), _two_boxes())

    assert patched_predictor.batch_calls == 1  # đã thử batch
    assert patched_predictor.predict_calls == 2  # fallback per-box 2 lần
    assert [line.text for line in lines] == ["perbox", "perbox"]


def test_per_box_mode_skips_batch(patched_predictor: FakePredictor) -> None:
    recognizer = rec_mod.RealTextRecognizer(batch=False)
    lines = recognizer.recognize(_image(), _two_boxes())

    assert patched_predictor.batch_calls == 0
    assert patched_predictor.predict_calls == 2
    assert len(lines) == 2


def test_single_box_uses_per_box_even_when_batch(patched_predictor: FakePredictor) -> None:
    recognizer = rec_mod.RealTextRecognizer(batch=True)
    lines = recognizer.recognize(_image(), [BBox(10, 10, 120, 45, 0.9)])

    # 1 box -> không cần batch.
    assert patched_predictor.batch_calls == 0
    assert patched_predictor.predict_calls == 1
    assert len(lines) == 1


def test_recognize_empty_boxes_returns_empty(patched_predictor: FakePredictor) -> None:
    recognizer = rec_mod.RealTextRecognizer(batch=True)
    assert recognizer.recognize(_image(), []) == []
    assert patched_predictor.batch_calls == 0
    assert patched_predictor.predict_calls == 0


def test_recognize_empty_image_raises(patched_predictor: FakePredictor) -> None:
    recognizer = rec_mod.RealTextRecognizer(batch=True)
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(rec_mod.OCRStageError):
        recognizer.recognize(empty, _two_boxes())


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        (0.5, 0.5),
        (1.5, 1.0),
        (-0.2, 0.0),
        ("not-a-number", None),
    ],
)
def test_safe_prob_normalizes(value, expected) -> None:  # noqa: ANN001
    result = rec_mod._safe_prob(value)
    assert result == (None if expected is None else pytest.approx(expected))
