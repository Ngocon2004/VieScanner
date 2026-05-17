from __future__ import annotations

from fastapi.testclient import TestClient


def test_register_login_me_happy_path(db_client: TestClient) -> None:
    register_payload = {
        "email": "test.auth@example.com",
        "password": "secret123",
        "full_name": "Test Auth",
    }
    register_res = db_client.post("/api/auth/register", json=register_payload)
    assert register_res.status_code == 200
    register_body = register_res.json()
    assert register_body["email"] == register_payload["email"]
    assert register_body["role"] == "user"

    login_res = db_client.post(
        "/api/auth/login",
        json={"email": register_payload["email"], "password": register_payload["password"]},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert token

    me_res = db_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_body = me_res.json()
    assert me_body["email"] == register_payload["email"]
    assert me_body["full_name"] == register_payload["full_name"]


def test_register_duplicate_email_returns_conflict(db_client: TestClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "password": "secret123",
        "full_name": "User One",
    }
    first = db_client.post("/api/auth/register", json=payload)
    assert first.status_code == 200

    second = db_client.post("/api/auth/register", json=payload)
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "email_exists"


def test_login_wrong_password_returns_unauthorized(db_client: TestClient) -> None:
    payload = {
        "email": "wrong-pass@example.com",
        "password": "secret123",
        "full_name": "Wrong Pass",
    }
    register = db_client.post("/api/auth/register", json=payload)
    assert register.status_code == 200

    login = db_client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": "bad-password"},
    )
    assert login.status_code == 401
    body = login.json()
    assert body["code"] == "auth_invalid"
