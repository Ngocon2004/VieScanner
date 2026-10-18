"""Tests cho OCR engine: semaphore giới hạn đồng thời (M1), warm-up (M2),
và /health readiness (M3)."""

from __future__ import annotations

import asyncio
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services import ocr_engine as eng_mod
from main import app


# ─────────────────────────────────────────────────────────────────────────────
# M1 – Semaphore giới hạn OCR đồng thời
# ─────────────────────────────────────────────────────────────────────────────


class _TrackingPipeline:
    """Pipeline giả ghi lại số coroutine `run` chạy đồng thời."""

    def __init__(self, state: dict[str, int]) -> None:
        self._state = state

    async def run(self, image_bytes: bytes):  # noqa: ANN201
        self._state["current"] += 1
        self._state["max"] = max(self._state["max"], self._state["current"])
        await asyncio.sleep(0.03)
        self._state["current"] -= 1
        return "ok"


async def _run_concurrent_extracts(limit: int, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(settings, "ocr_max_concurrency", limit)
    # Buộc tạo lại semaphore để đọc limit mới trên loop hiện tại.
    monkeypatch.setattr(eng_mod, "_ocr_semaphore", None)
    monkeypatch.setattr(eng_mod, "_ocr_semaphore_loop", None)

    state = {"current": 0, "max": 0}
    engine = eng_mod._PipelineEngine(_TrackingPipeline(state))
    await asyncio.gather(*[engine.extract(b"x") for _ in range(6)])
    assert state["current"] == 0
    return state["max"]


@pytest.mark.asyncio
async def test_semaphore_serializes_when_limit_one(monkeypatch: pytest.MonkeyPatch) -> None:
    max_concurrent = await _run_concurrent_extracts(1, monkeypatch)
    assert max_concurrent == 1


@pytest.mark.asyncio
async def test_semaphore_allows_configured_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    max_concurrent = await _run_concurrent_extracts(2, monkeypatch)
    assert max_concurrent == 2


@pytest.mark.asyncio
async def test_get_ocr_semaphore_uses_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ocr_max_concurrency", 3)
    monkeypatch.setattr(eng_mod, "_ocr_semaphore", None)
    monkeypatch.setattr(eng_mod, "_ocr_semaphore_loop", None)
    sem = eng_mod._get_ocr_semaphore()
    assert sem._value == 3
    # Gọi lại trên cùng loop -> trả về cùng instance (không tạo mới).
    assert eng_mod._get_ocr_semaphore() is sem


# ─────────────────────────────────────────────────────────────────────────────
# M2 – Warm-up models
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warmup_mock_engine_sets_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ocr_engine", "mock")
    monkeypatch.setattr(eng_mod, "_engine_ready", False)
    eng_mod._build_engine.cache_clear()

    ok = await eng_mod.warmup_ocr_engine()

    assert ok is True
    assert eng_mod.is_ocr_engine_ready() is True


@pytest.mark.asyncio
async def test_warmup_failure_sets_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> object:
        raise RuntimeError("cannot build engine")

    monkeypatch.setattr(eng_mod, "_build_engine", _boom)
    monkeypatch.setattr(eng_mod, "_engine_ready", True)

    ok = await eng_mod.warmup_ocr_engine()

    assert ok is False
    assert eng_mod.is_ocr_engine_ready() is False


# ─────────────────────────────────────────────────────────────────────────────
# M3 – /health readiness
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    # TestClient context chạy lifespan -> warm-up engine (mock) -> ready=True.
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_ocr_engine_fields(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "version" in body
    assert body["ocr_engine"] == settings.ocr_engine.lower()
    # Warm-up chạy ở startup (mock engine) nên engine đã sẵn sàng.
    assert body["ocr_engine_ready"] is True
