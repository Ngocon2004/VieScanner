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


def _valid_export_payload() -> dict[str, str]:
    return {
        "id_number": "001202000123",
        "full_name": "NGUYEN VAN A",
        "dob": "01/01/2002",
        "gender": "Nam",
        "nationality": "Viet Nam",
        "origin": "Quan 1, TP HCM",
        "residence": "123 Le Loi, Quan 1, TP HCM",
        "expiry_date": "01/01/2030",
    }


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "X-Request-ID" in response.headers


def test_extract_endpoint_success_with_mock_engine(client: TestClient) -> None:
    files = {"file": ("card.png", b"\x89PNG\r\n\x1a\nfake-image", "image/png")}
    response = client.post("/api/extract", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id_number"] == "001202000123"
    assert body["confidences"]["id_number"] == pytest.approx(0.99)
    assert "scan_id" in body
    assert "X-Request-ID" in response.headers


def test_extract_endpoint_rejects_invalid_mime(client: TestClient) -> None:
    files = {"file": ("card.txt", b"not-an-image", "text/plain")}
    response = client.post("/api/extract", files=files)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "image_invalid"
    assert "request_id" in body


def test_export_endpoint_returns_excel_file(client: TestClient) -> None:
    response = client.post("/api/export", json=_valid_export_payload())

    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"].startswith("attachment;")
    assert len(response.content) > 0
    assert "X-Request-ID" in response.headers


def test_export_endpoint_rejects_invalid_payload(client: TestClient) -> None:
    payload = _valid_export_payload()
    payload["id_number"] = "123"

    response = client.post("/api/export", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "details" in body
