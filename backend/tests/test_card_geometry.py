from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.image_quality import assess_image_quality
from app.services.ocr.card_geometry import CARD_ASPECT, find_card_quad, is_card_like
from app.services.ocr.interfaces import OCRStageError
from app.services.ocr.stages.aligner import RealCardAligner

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _photo_with_card(angle: float = 12.0, size: tuple[int, int] = (900, 1200)) -> "np.ndarray":
    """Nền tối có nhiễu + thẻ sáng bo góc, xoay `angle` độ."""
    img = np.random.default_rng(1).integers(20, 60, (*size, 3), dtype=np.uint8)
    w, h = 600, int(600 / CARD_ASPECT)
    card = np.zeros((h, w), dtype=np.uint8)
    r = 30
    cv2.rectangle(card, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(card, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(card, (cx, cy), r, 255, -1)
    canvas = np.zeros(size, dtype=np.uint8)
    y0, x0 = (size[0] - h) // 2, (size[1] - w) // 2
    canvas[y0 : y0 + h, x0 : x0 + w] = card
    rot = cv2.getRotationMatrix2D((size[1] / 2, size[0] / 2), angle, 1.0)
    mask = cv2.warpAffine(canvas, rot, (size[1], size[0]))
    img[mask > 127] = (225, 225, 225)
    return img


def _rect(w: float, h: float) -> "np.ndarray":
    return np.float32([[0, 0], [w, 0], [w, h], [0, h]])


@pytest.mark.parametrize(
    ("quad", "expected"),
    [
        (_rect(856, 540), True),
        (_rect(540, 856), True),  # thẻ xoay dọc
        (np.float32([[40, 0], [820, 30], [856, 540], [0, 520]]), True),  # chụp nghiêng nhẹ
        (_rect(500, 500), False),  # vuông, không phải tỉ lệ thẻ
        (np.float32([[0, 0], [856, 0], [500, 540], [300, 540]]), False),  # cạnh đối lệch nhiều
        (np.float32([[0, 0], [856, 0], [1200, 540], [344, 540]]), False),  # hình bình hành xiên
    ],
)
def test_is_card_like(quad: "np.ndarray", expected: bool) -> None:
    assert is_card_like(quad) is expected


def test_find_card_quad_locates_rotated_rounded_card() -> None:
    quad = find_card_quad(_photo_with_card())
    assert quad is not None
    assert is_card_like(quad)
    top = np.linalg.norm(quad[1] - quad[0])
    assert top == pytest.approx(600, rel=0.08)


@pytest.mark.parametrize("angle", [0.0, 45.0, -60.0, 90.0])
def test_find_card_quad_orders_corners_at_any_rotation(angle: float) -> None:
    quad = find_card_quad(_photo_with_card(angle=angle))
    assert quad is not None
    assert len({(round(float(x)), round(float(y))) for x, y in quad}) == 4
    assert int(np.argmin(quad.sum(axis=1))) == 0


def test_find_card_quad_returns_none_without_card() -> None:
    assert find_card_quad(np.random.default_rng(2).integers(20, 60, (600, 900, 3), dtype=np.uint8)) is None
    assert find_card_quad(np.zeros((0, 0, 3), dtype=np.uint8)) is None


def test_frame_hugging_quad_only_allowed_for_alignment() -> None:
    noise = np.random.default_rng(0).integers(20, 60, (600, 900, 3), dtype=np.uint8)
    assert find_card_quad(noise) is None
    frame = find_card_quad(noise, allow_frame=True)
    assert frame is not None
    assert is_card_like(frame)


def _aligner(monkeypatch: pytest.MonkeyPatch, corners: dict, *, contour: bool = True) -> RealCardAligner:
    aligner = RealCardAligner.__new__(RealCardAligner)
    aligner.conf_threshold = 0.25
    aligner.retry_conf_thresholds = ()
    aligner.allow_estimate_one = True
    aligner.contour_fallback = contour
    monkeypatch.setattr(
        RealCardAligner, "_best_corners", lambda *_a, **_k: {name: (0.9, point) for name, point in corners.items()}
    )
    return aligner


def _aspect(img: "np.ndarray") -> float:
    h, w = img.shape[:2]
    return max(w, h) / min(w, h)


def test_align_falls_back_to_card_outline_when_yolo_finds_no_corners(monkeypatch: pytest.MonkeyPatch) -> None:
    warped = _aligner(monkeypatch, {}).align(_photo_with_card())
    assert _aspect(warped) == pytest.approx(CARD_ASPECT, rel=0.1)


def test_align_prefers_card_outline_over_distorted_yolo_quad(monkeypatch: pytest.MonkeyPatch) -> None:
    skewed = {"top_left": (300, 200), "top_right": (900, 200), "bot_right": (1300, 700), "bot_left": (700, 700)}
    warped = _aligner(monkeypatch, skewed).align(_photo_with_card())
    assert _aspect(warped) == pytest.approx(CARD_ASPECT, rel=0.1)


def test_align_keeps_distorted_yolo_quad_when_no_outline_found(monkeypatch: pytest.MonkeyPatch) -> None:
    skewed = {"top_left": (10, 10), "top_right": (300, 10), "bot_right": (380, 200), "bot_left": (90, 200)}
    monkeypatch.setattr("app.services.ocr.stages.aligner.find_card_quad", lambda *_a, **_k: None)
    warped = _aligner(monkeypatch, skewed).align(np.zeros((400, 500, 3), dtype=np.uint8))
    assert warped.shape[:2] == (206, 290)


def test_align_falls_back_when_yolo_corners_collapse(monkeypatch: pytest.MonkeyPatch) -> None:
    tiny = {"top_left": (100, 100), "top_right": (104, 100), "bot_right": (104, 102), "bot_left": (100, 102)}
    warped = _aligner(monkeypatch, tiny).align(_photo_with_card())
    assert _aspect(warped) == pytest.approx(CARD_ASPECT, rel=0.1)


def test_align_raises_without_corners_when_fallback_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(OCRStageError):
        _aligner(monkeypatch, {}, contour=False).align(_photo_with_card())


def test_align_uses_card_like_yolo_quad_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    good = {"top_left": (100, 100), "top_right": (956, 100), "bot_right": (956, 640), "bot_left": (100, 640)}
    monkeypatch.setattr("app.services.ocr.stages.aligner.find_card_quad", lambda _img: pytest.fail("không cần đường viền"))
    warped = _aligner(monkeypatch, good).align(np.zeros((800, 1100, 3), dtype=np.uint8))
    assert warped.shape[:2] == (540, 856)


def test_quality_gate_softens_no_corners_when_card_outline_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.image_quality._count_card_corners", lambda _img: 0)
    monkeypatch.setattr(settings, "ocr_aligner_contour_fallback", True)
    ok, buf = cv2.imencode(".png", _photo_with_card())
    assert ok

    report = assess_image_quality(buf.tobytes(), run_card_check=True)

    assert not any(i.code == "not_cccd" for i in report.issues)
    assert any(i.code == "card_partial" and i.severity == "soft" for i in report.issues)
