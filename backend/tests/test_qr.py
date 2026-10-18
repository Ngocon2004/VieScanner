from __future__ import annotations

from typing import Any

import pytest

from app.services.ocr import pipeline as pipeline_module
from app.services.ocr.interfaces import OCRStageError
from app.services.ocr.pipeline import OCRPipeline
from app.services.ocr.qr import (
    CCCDQRData,
    parse_cccd_qr_payload,
    read_cccd_qr,
)
from app.services.ocr.stages import (
    MockAligner,
    MockCleaner,
    MockDetector,
    MockExtractor,
    MockRecognizer,
)

# QR mặt trước CCCD: số|CMND cũ|họ tên|ngày sinh|giới tính|nơi thường trú|ngày cấp
_VALID_PAYLOAD = (
    "012345678901|123456789|NGUYỄN VĂN A|01011990|Nam|"
    "Số 1, Phường Bến Nghé, Quận 1, TP. Hồ Chí Minh|15082021"
)


def _make_png_bytes() -> bytes:
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    image = np.zeros((96, 160, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Failed to encode test image")
    return encoded.tobytes()


class _EmptyDetector:
    def detect(self, image: Any) -> list[Any]:
        _ = image
        return []


class _FailingAligner:
    def align(self, image: Any) -> Any:
        _ = image
        raise OCRStageError("aligner", "forced failure")


# ── Parser ───────────────────────────────────────────────────────────────────


def test_parse_valid_payload_normalizes_fields() -> None:
    data = parse_cccd_qr_payload(_VALID_PAYLOAD)
    assert data is not None
    assert data.id_number == "012345678901"
    assert data.full_name == "NGUYỄN VĂN A"
    assert data.dob == "01/01/1990"  # ddmmyyyy -> dd/mm/yyyy
    assert data.gender == "Nam"
    assert data.residence.startswith("Số 1")
    assert data.issue_date == "15/08/2021"


def test_parse_payload_without_issue_date() -> None:
    payload = "012345678901||TRẦN THỊ B|31121985|Nữ|Hà Nội"
    data = parse_cccd_qr_payload(payload)
    assert data is not None
    assert data.gender == "Nữ"
    assert data.issue_date is None


@pytest.mark.parametrize(
    "payload",
    [
        "",
        None,
        "not-a-cccd-qr",
        "12345|123|Name|01011990|Nam|Addr",  # id sai (không đủ 12 số)
        "012345678901|123|Name|99999999|Nam|Addr",  # ngày sinh không hợp lệ
        "012345678901|123|Name|01011990|XYZ|Addr",  # giới tính không nhận ra
        "012345678901|123||01011990|Nam|Addr",  # thiếu họ tên
        "012345678901|123|Name|01011990|Nam|",  # thiếu nơi thường trú
    ],
)
def test_parse_invalid_payload_returns_none(payload: str | None) -> None:
    assert parse_cccd_qr_payload(payload) is None


def test_to_full_fields_fills_missing_with_defaults() -> None:
    data = parse_cccd_qr_payload(_VALID_PAYLOAD)
    assert data is not None
    full = data.to_full_fields()
    assert full["nationality"] == "Việt Nam"
    assert full["origin"]  # placeholder, non-empty
    assert "expiry_date" not in full  # QR không có hạn


# ── read_cccd_qr graceful ─────────────────────────────────────────────────────


def test_read_qr_on_blank_image_returns_none() -> None:
    import numpy as np

    blank = np.zeros((120, 200, 3), dtype=np.uint8)
    assert read_cccd_qr(blank) is None


def test_read_qr_on_invalid_input_returns_none() -> None:
    assert read_cccd_qr(None) is None  # type: ignore[arg-type]


def _qr_photo(payload: str) -> Any:
    import cv2  # type: ignore[import-untyped]
    import numpy as np
    import zxingcpp

    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    code = np.array(zxingcpp.write_barcode_to_image(barcode, scale=6))
    photo = np.full((code.shape[0] + 200, code.shape[1] + 300), 255, dtype=np.uint8)
    photo[100 : 100 + code.shape[0], 150 : 150 + code.shape[1]] = code
    return cv2.cvtColor(photo, cv2.COLOR_GRAY2BGR)


def test_read_qr_decodes_cccd_2021_payload() -> None:
    data = read_cccd_qr(_qr_photo(_VALID_PAYLOAD))
    assert data is not None
    assert data.id_number == "012345678901"
    assert data.full_name == "NGUYỄN VĂN A"


def test_read_qr_decodes_can_cuoc_2024_payload_with_11_parts() -> None:
    data = read_cccd_qr(_qr_photo(_VALID_PAYLOAD + "||||"))
    assert data is not None
    assert data.dob == "01/01/1990"
    assert data.issue_date == "15/08/2021"


def test_read_qr_falls_back_to_opencv_without_zxing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.ocr import qr as qr_module

    monkeypatch.setattr(qr_module, "_decode_zxing", lambda _img: None)
    monkeypatch.setattr(qr_module, "_decode_opencv", lambda _img: ["rác", _VALID_PAYLOAD])
    data = read_cccd_qr(_qr_photo("bất kỳ"))
    assert data is not None
    assert data.id_number == "012345678901"


# ── Pipeline integration ──────────────────────────────────────────────────────


def _mock_pipeline(detector: Any | None = None) -> OCRPipeline:
    return OCRPipeline(
        aligner=MockAligner(),
        cleaner=MockCleaner(),
        detector=detector or MockDetector(),
        recognizer=MockRecognizer(),
        extractor=MockExtractor(),
    )


@pytest.mark.asyncio
async def test_pipeline_qr_overrides_ocr_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    qr = parse_cccd_qr_payload(_VALID_PAYLOAD)
    assert qr is not None
    monkeypatch.setattr(pipeline_module, "read_cccd_qr", lambda _img: qr)

    result = await _mock_pipeline().run(_make_png_bytes())

    # QR ghi đè các trường nó cung cấp, confidence tuyệt đối.
    assert result.data.id_number == "012345678901"
    assert result.data.full_name == "NGUYỄN VĂN A"
    assert result.data.dob == "01/01/1990"
    assert result.data.gender == "Nam"
    assert result.confidences["id_number"] == 1.0
    assert result.confidences["full_name"] == 1.0
    assert result.confidences["residence"] == 1.0


@pytest.mark.asyncio
async def test_pipeline_qr_only_fallback_when_ocr_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qr = parse_cccd_qr_payload(_VALID_PAYLOAD)
    assert qr is not None
    monkeypatch.setattr(pipeline_module, "read_cccd_qr", lambda _img: qr)

    # Detector trả 0 box -> OCR fail, nhưng có QR -> trả dữ liệu QR-only.
    result = await _mock_pipeline(detector=_EmptyDetector()).run(_make_png_bytes())

    assert result.data.id_number == "012345678901"
    assert result.data.gender == "Nam"
    assert result.data.nationality == "Việt Nam"
    assert result.confidences["id_number"] == 1.0
    # Trường QR không cung cấp -> confidence 0 (user rà soát).
    assert result.confidences.get("origin", 0.0) == 0.0


@pytest.mark.asyncio
async def test_pipeline_qr_only_fallback_when_aligner_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qr = parse_cccd_qr_payload(_VALID_PAYLOAD)
    assert qr is not None
    monkeypatch.setattr(pipeline_module, "read_cccd_qr", lambda _img: qr)

    pipeline = OCRPipeline(
        aligner=_FailingAligner(),
        cleaner=MockCleaner(),
        detector=MockDetector(),
        recognizer=MockRecognizer(),
        extractor=MockExtractor(),
    )
    result = await pipeline.run(_make_png_bytes())
    assert result.data.id_number == "012345678901"


@pytest.mark.asyncio
async def test_pipeline_without_qr_keeps_ocr_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "read_cccd_qr", lambda _img: None)

    result = await _mock_pipeline().run(_make_png_bytes())

    # Không có QR -> giữ nguyên kết quả mock OCR (id mặc định của MockExtractor).
    assert result.data.id_number == "001202000123"
