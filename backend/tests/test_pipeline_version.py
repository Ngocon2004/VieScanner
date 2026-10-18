from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.ocr.version import engine_label, pipeline_version


def test_engine_label_includes_version_and_fits_column() -> None:
    label = engine_label(cached=True)
    assert label == f"{settings.ocr_engine}@{pipeline_version()}:cache"
    assert len(label) <= 32


def test_version_changes_with_output_affecting_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    before = pipeline_version()
    monkeypatch.setattr(settings, "ocr_detector_model", "PP-OCRv5_mobile_det")
    assert pipeline_version() != before


def test_version_ignores_runtime_only_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    before = pipeline_version()
    monkeypatch.setattr(settings, "ocr_result_cache_ttl_seconds", 1)
    monkeypatch.setattr(settings, "ocr_device", "cpu")
    assert pipeline_version() == before


class CountingEngine:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, image_bytes: bytes):  # noqa: ANN201
        from app.models.cccd import CCCDData, CCCDExtractResponse

        self.calls += 1
        return CCCDExtractResponse(
            data=CCCDData(
                id_number="001202000123", full_name="NGUYEN VAN A", dob="01/01/2002", gender="Nam",
                nationality="Viet Nam", origin="Thai Binh", residence="Thon 2, Xa A, Thai Binh",
            ),
            confidences=dict.fromkeys(("id_number", "full_name", "dob", "gender"), 0.9),
        )


@pytest.mark.asyncio
async def test_cache_hit_until_pipeline_version_changes(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    from app.db.repositories.scan_repository import ScanRepository
    from app.services import extraction
    from app.services.ocr import version

    monkeypatch.setattr(settings, "quality_check_enabled", False)
    monkeypatch.setattr(settings, "ocr_result_cache_enabled", True)
    repo, engine = ScanRepository(db_session), CountingEngine()

    async def scan_once() -> None:
        upload = extraction.make_upload("a.png", "image/png", b"same-image")
        outcome = await extraction.process_upload(
            index=0, upload=upload, engine=engine, repo=repo, seen={}, user_id=None
        )
        await repo.create_scan(request_id=None, **outcome.scan)
        await db_session.commit()

    await scan_once()
    await scan_once()
    assert engine.calls == 1

    monkeypatch.setattr(version, "pipeline_version", lambda: "newlogic")
    await scan_once()
    assert engine.calls == 2
