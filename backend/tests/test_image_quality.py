"""Unit tests cho cổng kiểm tra chất lượng ảnh (assess_image_quality)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.image_quality import assess_image_quality
from app.services.ocr.stages.aligner import RealCardAligner

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _encode_png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _good_image_bytes() -> bytes:
    # Ảnh đủ lớn + nhiều chi tiết (noise) => nét, sáng vừa, không lóa.
    img = np.random.randint(60, 200, (700, 1100, 3), dtype=np.uint8)
    return _encode_png(img)


def test_good_image_accepted() -> None:
    report = assess_image_quality(_good_image_bytes())
    assert report.accepted is True
    assert not report.has_hard_issue
    assert report.metrics["min_side_px"] == 700.0


def test_tiny_image_rejected_low_resolution() -> None:
    img = np.random.randint(60, 200, (90, 140, 3), dtype=np.uint8)
    report = assess_image_quality(_encode_png(img))
    assert report.accepted is False
    codes = {(i.code, i.severity) for i in report.issues}
    assert ("low_resolution", "hard") in codes


def test_dark_image_rejected() -> None:
    img = np.random.randint(0, 30, (700, 1100, 3), dtype=np.uint8)
    report = assess_image_quality(_encode_png(img))
    assert report.accepted is False
    assert any(i.code == "too_dark" and i.severity == "hard" for i in report.issues)


def test_uniform_image_flagged_blur() -> None:
    img = np.full((700, 1100, 3), 128, dtype=np.uint8)
    report = assess_image_quality(_encode_png(img))
    assert report.accepted is False
    assert any(i.code == "blur" and i.severity == "hard" for i in report.issues)


def test_undecodable_bytes_passthrough() -> None:
    report = assess_image_quality(b"\x89PNG\r\n\x1a\nnot-a-real-image")
    assert report.accepted is True
    assert report.issues == []


def test_disabled_check_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "quality_check_enabled", False)
    # Ảnh tí hon vốn sẽ bị loại, nhưng khi tắt check thì luôn pass.
    img = np.random.randint(60, 200, (40, 40, 3), dtype=np.uint8)
    report = assess_image_quality(_encode_png(img))
    assert report.accepted is True
    assert report.issues == []


def test_card_presence_rejects_when_no_corners(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.image_quality._count_card_corners", lambda _img: 0)

    report = assess_image_quality(_good_image_bytes(), run_card_check=True)

    assert report.accepted is False
    assert report.metrics["card_corners"] == 0.0
    assert any(i.code == "not_cccd" and i.severity == "hard" for i in report.issues)


def test_card_presence_warns_when_card_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.image_quality._count_card_corners", lambda _img: 2)

    report = assess_image_quality(_good_image_bytes(), run_card_check=True)

    assert report.accepted is True
    assert report.metrics["card_corners"] == 2.0
    assert any(i.code == "card_partial" and i.severity == "soft" for i in report.issues)


class _Tensor:
    def __init__(self, values) -> None:
        self.values = np.asarray(values, dtype=float)

    def cpu(self) -> "_Tensor":
        return self

    def numpy(self) -> np.ndarray:
        return self.values


class _FakeYolo:
    names = {0: "top_left", 1: "top_right", 2: "bot_right", 3: "bot_left"}

    def __init__(self) -> None:
        self.calls: list[float] = []

    def predict(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs["conf"])
        return [SimpleNamespace(boxes=_Boxes())]


class _Boxes:
    cls = _Tensor([0, 1, 2, 3, 0])
    conf = _Tensor([0.2, 0.2, 0.12, 0.3, 0.06])
    xyxy = _Tensor([[0, 0, 2, 2], [98, 0, 100, 2], [98, 60, 100, 62], [0, 60, 2, 62], [50, 50, 52, 52]])

    def __len__(self) -> int:
        return 5


def _yolo_aligner(monkeypatch: pytest.MonkeyPatch) -> tuple[RealCardAligner, _FakeYolo]:
    aligner = RealCardAligner.__new__(RealCardAligner)
    aligner.model_path, aligner.img_size, aligner.device = "fake.pt", 640, "cpu"
    aligner.conf_threshold = 0.25
    aligner.retry_conf_thresholds = (0.15, 0.10)
    aligner.allow_estimate_one = True
    model = _FakeYolo()
    monkeypatch.setattr("app.services.ocr.stages.aligner._load_yolo_model", lambda _path: model)
    return aligner, model


def test_count_corners_runs_yolo_once_at_lowest_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    aligner, model = _yolo_aligner(monkeypatch)
    assert aligner.count_corners(np.zeros((10, 10, 3), dtype=np.uint8)) == 4
    assert model.calls == [0.10]


def test_corner_thresholds_are_filtered_from_a_single_yolo_run(monkeypatch: pytest.MonkeyPatch) -> None:
    aligner, model = _yolo_aligner(monkeypatch)
    corners, tried = aligner._yolo_corners(np.zeros((70, 110, 3), dtype=np.uint8))
    # 0.25: chỉ có góc dưới-trái; 0.15: thiếu đúng 1 góc -> nội suy; box điểm thấp hơn của cùng góc bị bỏ.
    assert corners == {"top_left": (1, 1), "top_right": (99, 1), "bot_left": (1, 61), "bot_right": (99, 61)}
    assert len(tried) == 1
    assert model.calls == [0.10]
