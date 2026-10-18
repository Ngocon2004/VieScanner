from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.scan import ScanStatus
from app.db.models.user import User
from app.db.repositories.correction_repository import CorrectionRepository
from app.db.repositories.scan_repository import ScanRepository

OCR_DATA = {
    "id_number": "001202000123",
    "full_name": "NGUYEN VAN A",
    "dob": "01/01/2002",
    "gender": "Nam",
    "nationality": "Việt Nam",
    "origin": "Hà Nội",
    "residence": "Hà Nội",
}


def _login(client: TestClient, email: str) -> tuple[dict[str, str], str]:
    client.post("/api/auth/register", json={"email": email, "password": "secret123", "full_name": "T"})
    token = client.post("/api/auth/login", json={"email": email, "password": "secret123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, client.get("/api/auth/me", headers=headers).json()["id"]


def _make_admin(client: TestClient, factory: async_sessionmaker[AsyncSession], user_id: str) -> None:
    async def _run() -> None:
        async with factory() as session:
            await session.execute(update(User).where(User.id == user_id).values(role="admin"))
            await session.commit()

    client.portal.call(_run)


def _seed_scans(client: TestClient, factory: async_sessionmaker[AsyncSession], user_id: str) -> str:
    async def _run() -> str:
        async with factory() as session:
            repo = ScanRepository(session)
            common = dict(request_id=None, filename="a.jpg", mime_type="image/jpeg", size_bytes=1,
                          image_hash="h", ocr_engine="real", error_message=None)
            ok = await repo.create_scan(
                user_id=user_id, status=ScanStatus.SUCCESS, raw_data=OCR_DATA, error_code=None,
                confidences={"id_number": 1.0, "full_name": 0.6, "dob": 0.95, "residence": 0.0}, duration_ms=1200,
                **common,
            )
            await repo.create_scan(
                user_id=None, status=ScanStatus.FAILED, raw_data=None, confidences=None,
                error_code="image_quality_low", duration_ms=50, **common,
            )
            await CorrectionRepository(session).replace_for_scan(
                scan_id=ok.id,
                items=[{"field_name": "full_name", "ocr_value": "A", "corrected_value": "B", "confidence_at_ocr": 0.6}],
            )
            await session.commit()
            return ok.id

    return client.portal.call(_run)


def test_admin_routes_require_an_admin(db_client: TestClient, session_factory) -> None:
    assert db_client.get("/api/admin/overview").status_code == 401
    headers, _ = _login(db_client, "plain@example.com")
    assert db_client.get("/api/admin/overview", headers=headers).status_code == 403
    assert db_client.get("/api/admin/users", headers=headers).status_code == 403


def test_overview_counts_scans_errors_and_field_quality(db_client: TestClient, session_factory) -> None:
    headers, admin_id = _login(db_client, "admin@example.com")
    _make_admin(db_client, session_factory, admin_id)
    scan_id = _seed_scans(db_client, session_factory, admin_id)
    row = {"full_name": "NGUYỄN VĂN B", "id_number": "001202000123", "dob": "01/01/2002", "gender": "Nam",
           "residence": "Hà Nội", "scan_ids": [scan_id]}
    assert db_client.post("/api/export-list", json={"rows": [row]}, headers=headers).status_code == 200

    body = db_client.get("/api/admin/overview?days=7", headers=headers).json()
    totals = body["totals"]
    assert (totals["scans"], totals["succeeded"], totals["failed"]) == (2, 1, 1)
    assert totals["median_duration_ms"] == 1200
    assert totals["corrections"] == 1
    assert len(body["daily"]) == 7
    assert sum(d["success"] + d["failed"] for d in body["daily"]) == 2
    assert body["errors"] == [{"code": "image_quality_low", "count": 1}]
    fields = {f["field"]: f for f in body["fields"]}
    assert fields["full_name"]["read"] == 1 and fields["full_name"]["low_confidence"] == 1
    assert fields["full_name"]["corrected"] == 1 and fields["full_name"]["corrected_rate"] == 1.0
    assert totals["exported_scans"] == 1
    assert fields["residence"]["read"] == 0


def test_recent_scans_never_expose_raw_cccd_data(db_client: TestClient, session_factory) -> None:
    headers, admin_id = _login(db_client, "admin2@example.com")
    _make_admin(db_client, session_factory, admin_id)
    _seed_scans(db_client, session_factory, admin_id)

    items = db_client.get("/api/admin/scans", headers=headers).json()
    assert len(items) == 2
    success = next(i for i in items if i["status"] == "success")
    assert success["id_number_masked"] == "001******123"
    assert success["fields_read"] == 3 and success["low_confidence_fields"] == 1
    assert "NGUYEN" not in str(items) and "001202000123" not in str(items)
    failed = db_client.get("/api/admin/scans?status=failed", headers=headers).json()
    assert [i["error_code"] for i in failed] == ["image_quality_low"]


def test_admin_manages_users_but_cannot_demote_or_lock_itself(db_client: TestClient, session_factory) -> None:
    headers, admin_id = _login(db_client, "boss@example.com")
    _make_admin(db_client, session_factory, admin_id)
    _, member_id = _login(db_client, "member@example.com")

    users = {u["email"]: u for u in db_client.get("/api/admin/users", headers=headers).json()}
    assert users["member@example.com"]["role"] == "user"
    assert db_client.get("/api/admin/users?q=memb", headers=headers).json()[0]["id"] == member_id

    locked = db_client.patch(f"/api/admin/users/{member_id}", json={"is_active": False}, headers=headers)
    assert locked.status_code == 200 and locked.json()["is_active"] is False
    assert db_client.post("/api/auth/login", json={"email": "member@example.com", "password": "secret123"}).status_code == 401

    self_demote = db_client.patch(f"/api/admin/users/{admin_id}", json={"role": "user"}, headers=headers)
    assert self_demote.status_code == 409
    assert db_client.patch("/api/admin/users/missing", json={"role": "user"}, headers=headers).status_code == 404

    promoted = db_client.patch(f"/api/admin/users/{member_id}", json={"role": "admin", "is_active": True}, headers=headers)
    assert promoted.json()["role"] == "admin"


def test_system_status_reports_runtime_settings(db_client: TestClient, session_factory) -> None:
    headers, admin_id = _login(db_client, "ops@example.com")
    _make_admin(db_client, session_factory, admin_id)
    body = db_client.get("/api/admin/system", headers=headers).json()
    assert body["ocr_engine"] == "mock"
    assert {"queue_size", "pipeline_version", "qr_enabled"} <= body.keys()


def test_corrections_only_count_for_scans_marked_as_exported(db_client: TestClient, session_factory) -> None:
    headers, admin_id = _login(db_client, "rate@example.com")
    _make_admin(db_client, session_factory, admin_id)
    _seed_scans(db_client, session_factory, admin_id)
    body = db_client.get("/api/admin/overview", headers=headers).json()
    assert body["totals"]["corrections"] == 0
    assert all(f["corrected_rate"] <= 1 for f in body["fields"])


def test_overview_totals_match_daily_chart_and_only_list_exported_fields(db_client: TestClient, session_factory) -> None:
    headers, admin_id = _login(db_client, "window@example.com")
    _make_admin(db_client, session_factory, admin_id)
    _seed_scans(db_client, session_factory, admin_id)
    for days in (1, 7, 30):
        body = db_client.get(f"/api/admin/overview?days={days}", headers=headers).json()
        assert len(body["daily"]) == days
        assert body["totals"]["scans"] == sum(d["success"] + d["failed"] for d in body["daily"])
    assert [f["field"] for f in body["fields"]] == ["full_name", "id_number", "dob", "gender", "residence"]


def test_timestamps_carry_a_timezone_and_search_treats_wildcards_literally(
    db_client: TestClient, session_factory
) -> None:
    headers, admin_id = _login(db_client, "tz@example.com")
    _make_admin(db_client, session_factory, admin_id)
    _login(db_client, "other@example.com")
    _seed_scans(db_client, session_factory, admin_id)

    scan = db_client.get("/api/admin/scans", headers=headers).json()[0]
    assert scan["created_at"].endswith(("Z", "+00:00"))
    me = db_client.get("/api/auth/me", headers=headers).json()
    assert me["created_at"].endswith(("Z", "+00:00"))

    assert db_client.get("/api/admin/users?q=_", headers=headers).json() == []
    assert db_client.get("/api/admin/users?q=%25", headers=headers).json() == []
    assert len(db_client.get("/api/admin/users?q=example", headers=headers).json()) == 2
