from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cccd_record import CCCDRecord
from app.db.models.correction import Correction
from app.db.models.scan import Scan, ScanStatus
from app.db.repositories.scan_repository import ScanRepository
from app.db.repositories.user_repository import UserRepository


@pytest.mark.asyncio
async def test_create_and_list_scans_filtered_by_user(db_session: AsyncSession) -> None:
    user_repo = UserRepository(db_session)
    user_one = await user_repo.create_user(
        email="scan-one@example.com",
        password_hash="hash",
        full_name="Scan One",
    )
    user_two = await user_repo.create_user(
        email="scan-two@example.com",
        password_hash="hash",
        full_name="Scan Two",
    )
    await db_session.commit()

    repo = ScanRepository(db_session)
    await repo.create_scan(
        user_id=user_one.id,
        request_id="req-1",
        filename="scan-1.png",
        mime_type="image/png",
        size_bytes=100,
        image_hash="a" * 64,
        ocr_engine="mock",
        status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000123"},
        confidences={"id_number": 0.99},
        error_code=None,
        error_message=None,
        duration_ms=12,
    )
    await repo.create_scan(
        user_id=user_one.id,
        request_id="req-2",
        filename="scan-2.png",
        mime_type="image/png",
        size_bytes=101,
        image_hash="b" * 64,
        ocr_engine="mock",
        status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000124"},
        confidences={"id_number": 0.97},
        error_code=None,
        error_message=None,
        duration_ms=15,
    )
    await repo.create_scan(
        user_id=user_two.id,
        request_id="req-3",
        filename="scan-3.png",
        mime_type="image/png",
        size_bytes=102,
        image_hash="c" * 64,
        ocr_engine="mock",
        status=ScanStatus.FAILED,
        raw_data=None,
        confidences=None,
        error_code="ocr_failed",
        error_message="forced failure",
        duration_ms=20,
    )
    await db_session.commit()

    user_one_scans = await repo.list_by_user(user_id=user_one.id, limit=50, offset=0)
    assert len(user_one_scans) == 2
    assert all(scan.user_id == user_one.id for scan in user_one_scans)
    ids = {scan.request_id for scan in user_one_scans}
    assert ids == {"req-1", "req-2"}


@pytest.mark.asyncio
async def test_get_latest_success_by_image_hash(db_session: AsyncSession) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create_user(
        email="cache-user@example.com",
        password_hash="hash",
        full_name="Cache User",
    )
    await db_session.commit()

    repo = ScanRepository(db_session)
    image_hash = "z" * 64

    await repo.create_scan(
        user_id=user.id,
        request_id="req-failed",
        filename="failed.png",
        mime_type="image/png",
        size_bytes=10,
        image_hash=image_hash,
        ocr_engine="real",
        status=ScanStatus.FAILED,
        raw_data=None,
        confidences=None,
        error_code="ocr_failed",
        error_message="x",
        duration_ms=1,
    )
    await repo.create_scan(
        user_id=user.id,
        request_id="req-success-1",
        filename="ok1.png",
        mime_type="image/png",
        size_bytes=11,
        image_hash=image_hash,
        ocr_engine="real",
        status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000123"},
        confidences={"id_number": 0.91},
        error_code=None,
        error_message=None,
        duration_ms=2,
    )
    await asyncio.sleep(1.05)
    await repo.create_scan(
        user_id=user.id,
        request_id="req-success-2",
        filename="ok2.png",
        mime_type="image/png",
        size_bytes=12,
        image_hash=image_hash,
        ocr_engine="real",
        status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000124"},
        confidences={"id_number": 0.92},
        error_code=None,
        error_message=None,
        duration_ms=3,
    )
    await db_session.commit()

    cached = await repo.get_latest_success_by_image_hash(
        image_hash=image_hash,
        user_id=user.id,
        ttl_seconds=3600,
    )
    assert cached is not None
    assert cached.request_id == "req-success-2"
    assert cached.status == ScanStatus.SUCCESS
    assert cached.raw_data == {"id_number": "001202000124"}


@pytest.mark.asyncio
async def test_create_scan_with_explicit_id(db_session: AsyncSession) -> None:
    """M4: caller pre-generate scan_id để trả ngay rồi ghi nền."""
    repo = ScanRepository(db_session)
    fixed_id = "11111111-1111-1111-1111-111111111111"

    scan = await repo.create_scan(
        id=fixed_id,
        user_id=None,
        request_id=None,
        filename="a.png",
        mime_type="image/png",
        size_bytes=10,
        image_hash="a" * 64,
        ocr_engine="mock",
        status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000123"},
        confidences={},
        error_code=None,
        error_message=None,
        duration_ms=5,
    )
    await db_session.commit()

    assert scan.id == fixed_id
    fetched = await repo.get_by_id(fixed_id)
    assert fetched is not None
    assert fetched.id == fixed_id


@pytest.mark.asyncio
async def test_delete_older_than_removes_old_and_cascades(db_session: AsyncSession) -> None:
    """M5: xóa scan cũ + dọn corrections, gỡ liên kết cccd_records (giữ record)."""
    now = datetime.now(timezone.utc)
    old = Scan(
        ocr_engine="real",
        status=ScanStatus.SUCCESS,
        created_at=now - timedelta(days=40),
    )
    recent = Scan(
        ocr_engine="real",
        status=ScanStatus.SUCCESS,
        created_at=now - timedelta(days=1),
    )
    db_session.add_all([old, recent])
    await db_session.flush()  # gán id

    correction = Correction(
        scan_id=old.id,
        field_name="full_name",
        ocr_value="NGUYEN VAN A",
        corrected_value="NGUYỄN VĂN A",
    )
    record = CCCDRecord(
        scan_id=old.id,
        id_number="001202000123",
        full_name="NGUYEN VAN A",
        dob=date(2002, 1, 1),
        gender="Nam",
        nationality="Viet Nam",
        origin="Quan 1",
        residence="123 Le Loi",
    )
    db_session.add_all([correction, record])
    await db_session.commit()

    repo = ScanRepository(db_session)
    deleted = await repo.delete_older_than(now - timedelta(days=30))
    await db_session.commit()

    assert deleted == 1
    assert await repo.get_by_id(old.id) is None
    assert await repo.get_by_id(recent.id) is not None

    # Correction con bị xóa theo.
    remaining_corr = (
        await db_session.execute(
            select(Correction).where(Correction.id == correction.id)
        )
    ).scalar_one_or_none()
    assert remaining_corr is None

    # Record được giữ lại nhưng gỡ liên kết scan (scan_id -> NULL).
    refreshed = (
        await db_session.execute(
            select(CCCDRecord).where(CCCDRecord.id == record.id)
        )
    ).scalar_one_or_none()
    assert refreshed is not None
    assert refreshed.scan_id is None




@pytest.mark.asyncio
async def test_cache_lookup_ignores_results_from_another_engine(db_session: AsyncSession) -> None:
    repo = ScanRepository(db_session)
    common = dict(
        user_id=None, request_id=None, filename="c.png", mime_type="image/png",
        size_bytes=1, image_hash="e" * 64, status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000123"}, confidences={},
        error_code=None, error_message=None, duration_ms=1,
    )
    await repo.create_scan(ocr_engine="mock", **common)
    await db_session.commit()

    assert await repo.get_latest_success_by_image_hash(
        image_hash="e" * 64, user_id=None, ocr_engine="real"
    ) is None
    assert await repo.get_latest_success_by_image_hash(
        image_hash="e" * 64, user_id=None, ocr_engine="mock"
    ) is not None

    # Dòng ghi lại từ một lần trúng cache không được dùng làm cache tiếp (tránh tự gia hạn TTL).
    await repo.create_scan(ocr_engine="real:cache", **common)
    await db_session.commit()
    assert await repo.get_latest_success_by_image_hash(
        image_hash="e" * 64, user_id=None, ocr_engine="real"
    ) is None


@pytest.mark.asyncio
async def test_cache_lookup_ignores_results_from_older_pipeline_version(db_session: AsyncSession) -> None:
    repo = ScanRepository(db_session)
    await repo.create_scan(
        ocr_engine="real@0000aaaa", user_id=None, request_id=None, filename="c.png", mime_type="image/png",
        size_bytes=1, image_hash="f" * 64, status=ScanStatus.SUCCESS,
        raw_data={"id_number": "001202000123"}, confidences={},
        error_code=None, error_message=None, duration_ms=1,
    )
    await db_session.commit()
    assert await repo.get_latest_success_by_image_hash(
        image_hash="f" * 64, user_id=None, ocr_engine="real@1111bbbb"
    ) is None
