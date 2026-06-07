"""API tests cho /extract-batch + quality gate ở /extract."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.models.cccd import CCCDData, CCCDExtractResponse
from app.services.ocr_engine import get_ocr_engine
from main import app


class DummyOCREngine:
    async def extract(self, image_bytes: bytes) -> CCCDExtractResponse:
        _ = image_bytes
        return CCCDExtractResponse(
            data=CCCDData(
                id_number="001202000123",
                full_name="NGUYEN VAN A",
                dob="01/01/2002",
                gender="Nam",
                nationality="Viet Nam",
                origin="Quan 1, TP HCM",
                residence="123 Le Loi, Quan 1, TP HCM",
                expiry_date="01/01/2030",
            ),
            confidences={"id_number": 0.99, "full_name": 0.92},
        )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_ocr_engine] = lambda: DummyOCREngine()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# Ảnh PNG giả: magic bytes hợp lệ nhưng không decode được -> quality passthrough.
_FAKE_PNG = b"\x89PNG\r\n\x1a\nfake-image"


def test_batch_all_valid(client: TestClient) -> None:
    files = [
        ("files", ("a.png", _FAKE_PNG, "image/png")),
        ("files", ("b.png", _FAKE_PNG, "image/png")),
    ]
    response = client.post("/api/extract-batch", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["accepted_count"] == 2
    assert body["rejected_count"] == 0
    assert all(r["status"] == "extracted" for r in body["results"])
    assert body["results"][0]["data"]["id_number"] == "001202000123"
    # index theo thứ tự upload
    assert [r["index"] for r in body["results"]] == [0, 1]


def test_batch_mixed_valid_and_invalid_mime(client: TestClient) -> None:
    files = [
        ("files", ("good.png", _FAKE_PNG, "image/png")),
        ("files", ("bad.txt", b"not-an-image", "text/plain")),
    ]
    response = client.post("/api/extract-batch", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["accepted_count"] == 1
    assert body["rejected_count"] == 1

    rejected = [r for r in body["results"] if not r["accepted"]]
    assert len(rejected) == 1
    assert rejected[0]["status"] == "rejected"
    assert rejected[0]["error_code"] == "image_invalid"


def test_batch_rejects_when_too_many_files(client: TestClient) -> None:
    from app.core.config import settings

    files = [
        ("files", (f"f{i}.png", _FAKE_PNG, "image/png"))
        for i in range(settings.quality_max_batch_files + 1)
    ]
    response = client.post("/api/extract-batch", files=files)
    assert response.status_code == 400
    assert response.json()["code"] == "image_invalid"


def test_single_extract_includes_quality(client: TestClient) -> None:
    files = {"file": ("card.png", _FAKE_PNG, "image/png")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 200
    body = response.json()
    # Ảnh giả không decode được -> quality passthrough accepted.
    assert body["quality"]["accepted"] is True


def test_single_extract_rejects_low_quality_image(client: TestClient) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    tiny = np.random.randint(60, 200, (60, 90, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", tiny)
    assert ok

    files = {"file": ("tiny.png", buf.tobytes(), "image/png")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "image_quality_low"
    assert body["details"]
    assert any(d["code"] == "low_resolution" for d in body["details"])
