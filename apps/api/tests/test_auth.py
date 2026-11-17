from fastapi.testclient import TestClient

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hashing() -> None:
    pw = "SuperSecretPassword123!"
    hashed = hash_password(pw)

    assert hashed.startswith("pbkdf2:sha256:100000$")
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_creation_and_decoding() -> None:
    token = create_access_token(
        subject="user-123",
        claims={"email": "test@example.com", "role": "user"},
        expires_minutes=60,
    )
    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@example.com"
    assert payload["role"] == "user"


def test_user_registration_and_login(client: TestClient) -> None:
    reg_data = {
        "email": "anupam@example.com",
        "password": "StrongPassword123!",
        "full_name": "Anupam DS",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    assert reg_res.status_code == 201
    reg_json = reg_res.json()
    assert "access_token" in reg_json
    assert reg_json["email"] == "anupam@example.com"
    assert reg_json["consent_given"] is True

    # Duplicate registration should return 409 Conflict
    dup_res = client.post("/api/v1/auth/register", json=reg_data)
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "CONFLICT"

    # Login with valid credentials
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "anupam@example.com", "password": "StrongPassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # Retrieve profile with token
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_json = me_res.json()
    assert me_json["email"] == "anupam@example.com"
    assert me_json["consent"]["terms_accepted"] is True


def test_unauthorized_endpoints(client: TestClient) -> None:
    # Accessing protected endpoint without token returns 401 with unified error format
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"
    assert "request_id" in res.json()["error"]
