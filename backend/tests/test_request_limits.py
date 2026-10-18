from __future__ import annotations

from collections.abc import Generator, Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.core.config import settings
from main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def one_mb_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_request_mb", 1)
    entry = next(m for m in app.user_middleware if m.cls is RequestBodyLimitMiddleware)
    monkeypatch.setitem(entry.kwargs, "max_body_size", settings.max_request_bytes)
    monkeypatch.setattr(app, "middleware_stack", None)


def _assert_too_large(response) -> None:
    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "request_too_large"
    assert "1MB" in body["message"]
    assert response.headers["X-Request-ID"] == body["request_id"]


@pytest.mark.usefixtures("one_mb_limit")
def test_declared_oversized_body_is_rejected_before_reading(client: TestClient) -> None:
    response = client.post(
        "/api/extract-batch",
        content=b"x",
        headers={"Content-Type": "multipart/form-data; boundary=b", "Content-Length": str(2 * 1024 * 1024)},
    )
    _assert_too_large(response)


@pytest.mark.usefixtures("one_mb_limit")
def test_chunked_body_over_limit_is_rejected(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b"--b\r\nContent-Disposition: form-data; name=\"files\"; filename=\"a.png\"\r\n\r\n"
        for _ in range(3):
            yield b"0" * (512 * 1024)
        yield b"\r\n--b--\r\n"

    response = client.post(
        "/api/extract-batch", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=b"}
    )
    _assert_too_large(response)


def test_urlencoded_field_is_capped_like_multipart(client: TestClient) -> None:
    # CVE-2026-54283: starlette < 1.3.1 đọc trọn trường urlencoded bất kể max_part_size (1MB).
    response = client.post(
        "/api/jobs",
        content=b"source=" + b"a" * (2 * 1024 * 1024),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
