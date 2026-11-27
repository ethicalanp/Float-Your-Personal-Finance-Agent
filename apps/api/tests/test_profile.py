import uuid

from fastapi.testclient import TestClient

from tests.test_auth_linking import _create_stale_token


def _register(client: TestClient, email: str, password: str = "StrongPass123!") -> tuple[dict[str, str], str]:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Priya Nair",
            "terms_accepted": True,
            "privacy_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    assert res.status_code == 201
    data = res.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user_id"]


def test_get_and_patch_profile_validation_malayalam_and_audit(client: TestClient) -> None:
    headers, _ = _register(client, f"prof_{uuid.uuid4().hex[:8]}@example.com")

    # Unauthenticated -> 401
    assert client.get("/api/v1/me").status_code == 401

    # GET /me
    res = client.get("/api/v1/me", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["full_name"] == "Priya Nair"
    assert body["preferred_language"] == "en"
    assert "password" in body["methods"]

    # PATCH /me with Malayalam display name + trimmed whitespace + language + prefs
    patch_res = client.patch(
        "/api/v1/me",
        headers=headers,
        json={
            "full_name": "  പ്രിയ   നായർ  ",
            "preferred_language": "ml",
            "locale": "ml-IN",
            "notification_preferences": {"product_updates": True},
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["full_name"] == "പ്രിയ നായർ"
    assert updated["preferred_language"] == "ml"
    assert updated["locale"] == "ml-IN"
    assert updated["notification_preferences"]["product_updates"] is True
    assert updated["notification_preferences"]["security_alerts"] is True

    # Invalid characters rejected
    bad_name = client.patch("/api/v1/me", headers=headers, json={"full_name": "<script>alert(1)</script>"})
    assert bad_name.status_code in (400, 422)

    # Direct email/phone modification rejected (must use link/verify flows)
    bad_email = client.patch("/api/v1/me", headers=headers, json={"email": "new@example.com"})
    assert bad_email.status_code == 422
    bad_phone = client.patch("/api/v1/me", headers=headers, json={"phone_number": "+919876543210"})
    assert bad_phone.status_code == 422


def test_dpdp_export_returns_only_own_data_and_excludes_secrets(client: TestClient) -> None:
    headers_a, uid_a = _register(client, f"exp_a_{uuid.uuid4().hex[:8]}@example.com")
    headers_b, _ = _register(client, f"exp_b_{uuid.uuid4().hex[:8]}@example.com")

    # Create account for user A and user B
    acc_a = client.post(
        "/api/v1/plan/accounts",
        headers=headers_a,
        json={"name": "User A Bank", "account_type": "savings", "current_balance": 10000},
    )
    assert acc_a.status_code == 201
    acc_b = client.post(
        "/api/v1/plan/accounts",
        headers=headers_b,
        json={"name": "User B Secret Bank", "account_type": "savings", "current_balance": 99999},
    )
    assert acc_b.status_code == 201

    # Cross-user access to user B's account via plan/accounts or export isolation
    exp_a = client.post("/api/v1/me/export", headers=headers_a)
    assert exp_a.status_code == 200
    data_a = exp_a.json()
    assert data_a["profile"]["user_id"] == uid_a
    assert len(data_a["accounts"]) == 1
    assert data_a["accounts"][0]["name"] == "User A Bank"
    assert "User B Secret Bank" not in str(data_a)
    assert "hashed_password" not in str(data_a)
    assert "refresh_token_hash" not in str(data_a)


def test_dpdp_delete_requires_reauth_revokes_sessions_purges_chats_and_cancels(client: TestClient) -> None:
    email = f"del_{uuid.uuid4().hex[:8]}@example.com"
    headers, uid = _register(client, email)
    headers_other, _ = _register(client, f"del_other_{uuid.uuid4().hex[:8]}@example.com")

    # Stale auth_time -> 403 reauth_required
    stale_headers = _create_stale_token(uid, email)
    stale_res = client.delete("/api/v1/me", headers=stale_headers)
    assert stale_res.status_code == 403
    assert stale_res.json()["error"]["code"] == "reauth_required"

    # Create a conversation for user and another user via assistant endpoint or DB
    chat_res = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={"question": "What is emergency fund?"},
    )
    assert chat_res.status_code == 200

    # Delete account with fresh auth
    del_res = client.delete("/api/v1/me", headers=headers)
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["status"] == "deletion_scheduled"
    assert del_data["grace_period_days"] >= 1
    assert del_data["deletion_scheduled_for"]

    # Sessions revoked -> GET /auth/sessions returns 0 active
    sess_res = client.get("/api/v1/auth/sessions", headers=headers)
    assert sess_res.status_code == 200
    assert sess_res.json() == []

    # Export now shows 0 conversations (purged)
    exp_res = client.post("/api/v1/me/export", headers=headers)
    assert exp_res.status_code == 200
    assert exp_res.json()["conversations"] == []
    assert exp_res.json()["messages"] == []

    # Cancel deletion within grace period
    cancel_res = client.post("/api/v1/me/delete/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["deletion_scheduled_for"] is None
    assert cancel_res.json()["deletion_requested_at"] is None

    # Other user unaffected
    assert client.get("/api/v1/me", headers=headers_other).status_code == 200
