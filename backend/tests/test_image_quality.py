"""Unit tests cho cổng kiểm tra chất lượng ảnh (assess_image_quality)."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.image_quality import assess_image_quality

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
