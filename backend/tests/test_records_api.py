from __future__ import annotations

from fastapi.testclient import TestClient


def _auth_headers(client: TestClient, email: str) -> dict[str, str]:
    register = client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123", "full_name": "Record Tester"},
    )
    assert register.status_code == 200

    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_records_crud_happy_path(db_client: TestClient) -> None:
    headers = _auth_headers(db_client, "records@example.com")

    create_payload = {
        "id_number": "001202000123",
        "full_name": "NGUYEN VAN A",
        "dob": "01/01/2002",
        "gender": "Nam",
        "nationality": "Viet Nam",
        "origin": "Quan 1, TP HCM",
        "residence": "123 Le Loi, Quan 1, TP HCM",
        "expiry_date": "01/01/2030",
    }
    create_res = db_client.post("/api/records", json=create_payload, headers=headers)
    assert create_res.status_code == 200
    created = create_res.json()
    record_id = created["id"]
    assert created["id_number"] == create_payload["id_number"]

    list_res = db_client.get("/api/records", headers=headers)
    assert list_res.status_code == 200
    records = list_res.json()
    assert len(records) == 1
    assert records[0]["id"] == record_id

    patch_res = db_client.patch(
        f"/api/records/{record_id}",
        json={"full_name": "NGUYEN VAN B"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["full_name"] == "NGUYEN VAN B"

    delete_res = db_client.delete(f"/api/records/{record_id}", headers=headers)
    assert delete_res.status_code == 200
    assert delete_res.json()["status"] == "deleted"

    list_after_delete = db_client.get("/api/records", headers=headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json() == []
