from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.scan import ScanStatus
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

