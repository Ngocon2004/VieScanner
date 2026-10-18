from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models.job import JobItemStatus, JobSource
from app.db.models.scan import ScanStatus
from app.db.repositories.job_repository import JobRepository
from app.db.repositories.scan_repository import ScanRepository
from app.db.session import _create_engine

RECORD = {
    "id_number": "001202000123",
    "full_name": "NGUYEN VAN A",
    "dob": "01/01/2002",
    "gender": "Nam",
    "nationality": "Việt Nam",
    "origin": "Hà Nội",
    "residence": "Hà Nội",
}


async def _scan(session: AsyncSession, **overrides) -> str:
    scan = await ScanRepository(session).create_scan(
        **{
            "user_id": None, "request_id": None, "filename": "a.jpg", "mime_type": "image/jpeg",
            "size_bytes": 1, "image_hash": "h", "ocr_engine": "mock", "status": ScanStatus.SUCCESS,
            "raw_data": RECORD, "confidences": {}, "error_code": None, "error_message": None,
            "duration_ms": 1, **overrides,
        }
    )
    return scan.id


@pytest.mark.asyncio
async def test_app_engine_enforces_sqlite_foreign_keys(tmp_path) -> None:
    engine = _create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'fk.db').as_posix()}", echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_jobs_and_old_scans_leaves_no_dangling_links(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        jobs = JobRepository(session)
        job = await jobs.create(
            user_id=None, source=JobSource.UPLOAD, ocr_engine="mock",
            items=[{"upload_index": 0, "filename": "a.jpg", "status": JobItemStatus.DONE}],
        )
        scan_id = await _scan(session, job_id=job.id)
        job.items[0].scan_id = scan_id
        await session.commit()
        job_id = job.id

        await ScanRepository(session).delete_older_than(datetime.now(timezone.utc) + timedelta(days=1))
        await session.commit()
        item_scan = (await session.execute(text("select scan_id from job_items"))).scalar_one()
        assert item_scan is None

        other_scan = await _scan(session, job_id=job_id)
        await session.commit()
        await jobs.delete(job_id)
        await session.commit()
        assert (await ScanRepository(session).get_by_id(other_scan)).job_id is None


def test_record_with_unknown_scan_is_saved_without_link(db_client: TestClient) -> None:
    db_client.post(
        "/api/auth/register",
        json={"email": "fk@example.com", "password": "secret123", "full_name": "FK"},
    )
    token = db_client.post(
        "/api/auth/login", json={"email": "fk@example.com", "password": "secret123"}
    ).json()["access_token"]
    res = db_client.post(
        "/api/records",
        json={**RECORD, "scan_id": "does-not-exist"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["scan_id"] is None


def test_signed_token_without_subject_is_401_not_500(db_client: TestClient) -> None:
    token = jwt.encode(
        {"type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    res = db_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    # Frontend dựa vào mã này để xóa token hết hạn và gửi lại request ẩn danh.
    assert res.json()["code"] == "auth_token_invalid"


def test_default_jwt_secret_is_never_used() -> None:
    from app.core.config import Settings

    assert Settings(jwt_secret="CHANGE_ME").jwt_secret != "CHANGE_ME"
    assert Settings(jwt_secret="a-real-secret-value").jwt_secret == "a-real-secret-value"
