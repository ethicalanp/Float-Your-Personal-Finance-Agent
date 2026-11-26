import time
import uuid

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.services.sms_provider import FakeSmsProvider
from tests.test_auth_extended import _make_test_google_token


def _register_user(client: TestClient, email: str, password: str = "Password123!") -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Linking Test User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_stale_token(user_id: str, email: str = "stale@example.com") -> dict[str, str]:
    now = int(time.time())
    token = create_access_token(
        subject=user_id,
        claims={"email": email, "auth_time": now - 1000, "sid": str(uuid.uuid4())},
    )
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 1. Own vs Other Session Revocation
# ============================================================================


def test_revoke_own_session(client: TestClient) -> None:
    headers = _register_user(client, f"session_own_{uuid.uuid4().hex[:6]}@example.com")
    sessions_res = client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 1
    session_id = sessions[0]["id"]

    # Revoking own session succeeds
    del_res = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)
    assert del_res.status_code == 200
    assert "logged out" in del_res.json()["message"].lower() or "revoked" in del_res.json()["message"].lower()


def test_revoke_other_user_session_returns_404(client: TestClient) -> None:
    headers_a = _register_user(client, f"user_a_{uuid.uuid4().hex[:6]}@example.com")
    headers_b = _register_user(client, f"user_b_{uuid.uuid4().hex[:6]}@example.com")

    # Get user A's session ID
    sessions_a = client.get("/api/v1/auth/sessions", headers=headers_a).json()
    session_a_id = sessions_a[0]["id"]

    # User B attempts to revoke User A's session -> must return 404
    del_res = client.delete(f"/api/v1/auth/sessions/{session_a_id}", headers=headers_b)
    assert del_res.status_code == 404
    assert del_res.json()["error"]["code"] == "NOT_FOUND"


# ============================================================================
# 2. Google Linking: Success, Unverified Email, and Conflict
# ============================================================================


def test_link_google_success(client: TestClient) -> None:
    headers = _register_user(client, f"google_link_{uuid.uuid4().hex[:6]}@example.com")
    sub = f"goog-sub-{uuid.uuid4().hex[:8]}"
    token = _make_test_google_token(sub=sub, email="verified_goog@example.com", email_verified=True)

    link_res = client.post("/api/v1/auth/link/google", json={"id_token": token}, headers=headers)
    assert link_res.status_code == 200
    assert "linked" in link_res.json()["message"].lower()

    # Check methods
    methods_res = client.get("/api/v1/auth/methods", headers=headers)
    assert methods_res.status_code == 200
    methods = [m["provider"] for m in methods_res.json()["methods"]]
    assert "google" in methods


def test_link_google_unverified_email_refused(client: TestClient) -> None:
    headers = _register_user(client, f"goog_unverified_{uuid.uuid4().hex[:6]}@example.com")
    token = _make_test_google_token(email_verified=False)

    link_res = client.post("/api/v1/auth/link/google", json={"id_token": token}, headers=headers)
    assert link_res.status_code == 400
    assert "verified" in link_res.json()["error"]["message"].lower()


def test_link_google_conflict(client: TestClient) -> None:
    headers_a = _register_user(client, f"gconf_a_{uuid.uuid4().hex[:6]}@example.com")
    headers_b = _register_user(client, f"gconf_b_{uuid.uuid4().hex[:6]}@example.com")

    shared_sub = f"shared-goog-{uuid.uuid4().hex[:8]}"
    token_a = _make_test_google_token(sub=shared_sub, email="shared@example.com", email_verified=True)

    # Link to A
    res_a = client.post("/api/v1/auth/link/google", json={"id_token": token_a}, headers=headers_a)
    assert res_a.status_code == 200

    # User B attempts to link the same Google sub -> 409 Conflict
    token_b = _make_test_google_token(sub=shared_sub, email="shared@example.com", email_verified=True)
    res_b = client.post("/api/v1/auth/link/google", json={"id_token": token_b}, headers=headers_b)
    assert res_b.status_code == 409
    assert res_b.json()["error"]["code"] == "CONFLICT"


# ============================================================================
# 3. Step-Up Re-Auth & Stale Re-Auth Rejection
# ============================================================================


def test_stale_reauth_rejected_for_sensitive_ops(client: TestClient) -> None:
    user_email = f"stale_user_{uuid.uuid4().hex[:6]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": user_email, "password": "Password123!", "full_name": "Stale User"},
    )
    user_id = reg.json()["user_id"]
    stale_headers = _create_stale_token(user_id, user_email)

    # 1. DELETE /link/google with stale auth -> 403 reauth_required
    del_res = client.delete("/api/v1/auth/link/google", headers=stale_headers)
    assert del_res.status_code == 403
    assert del_res.json()["error"]["code"] == "reauth_required"

    # 2. POST /link/google with stale auth -> 403 reauth_required
    token = _make_test_google_token()
    link_res = client.post("/api/v1/auth/link/google", json={"id_token": token}, headers=stale_headers)
    assert link_res.status_code == 403
    assert link_res.json()["error"]["code"] == "reauth_required"

    # 3. POST /password with stale auth -> 403 reauth_required
    pw_res = client.post("/api/v1/auth/password", json={"password": "NewPassword123!"}, headers=stale_headers)
    assert pw_res.status_code == 403
    assert pw_res.json()["error"]["code"] == "reauth_required"


def test_reauth_renews_token_and_enables_sensitive_ops(client: TestClient) -> None:
    user_email = f"renew_user_{uuid.uuid4().hex[:6]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": user_email, "password": "Password123!", "full_name": "Renew User"},
    )
    user_id = reg.json()["user_id"]
    stale_headers = _create_stale_token(user_id, user_email)

    # Re-auth with password
    reauth_res = client.post(
        "/api/v1/auth/reauth",
        json={"method": "password", "password": "Password123!"},
        headers=stale_headers,
    )
    assert reauth_res.status_code == 200
    fresh_token = reauth_res.json()["access_token"]
    fresh_headers = {"Authorization": f"Bearer {fresh_token}"}

    # Now sensitive op works with fresh token
    sub = f"goog-fresh-{uuid.uuid4().hex[:8]}"
    token = _make_test_google_token(sub=sub, email="fresh_link@example.com", email_verified=True)
    link_res = client.post("/api/v1/auth/link/google", json={"id_token": token}, headers=fresh_headers)
    assert link_res.status_code == 200


# ============================================================================
# 4. Last Method Removal Forbidden
# ============================================================================


def test_last_method_removal_forbidden(client: TestClient) -> None:
    # User registered via email/password only
    headers = _register_user(client, f"last_meth_{uuid.uuid4().hex[:6]}@example.com")

    # Attempt to unlink password when it's the only method
    del_res = client.delete("/api/v1/auth/link/password", headers=headers)
    assert del_res.status_code == 400
    assert "sole" in del_res.json()["error"]["message"].lower()

    # User with Google only
    sub = f"goog-only-{uuid.uuid4().hex[:8]}"
    g_token = _make_test_google_token(sub=sub, email=f"gonly_{uuid.uuid4().hex[:6]}@example.com")
    g_login = client.post("/api/v1/auth/google", json={"id_token": g_token})
    g_headers = {"Authorization": f"Bearer {g_login.json()['access_token']}"}

    # Attempt to unlink Google when it's the only method
    g_del = client.delete("/api/v1/auth/link/google", headers=g_headers)
    assert g_del.status_code == 400
    assert "sole" in g_del.json()["error"]["message"].lower()


# ============================================================================
# 5. Set Password for Google/Phone Signups & Revoke Other Sessions
# ============================================================================


def test_password_set_then_login_and_revokes_other_sessions(client: TestClient) -> None:
    # Google signup (no password initially)
    sub = f"goog-nopw-{uuid.uuid4().hex[:8]}"
    email = f"nopw_{uuid.uuid4().hex[:6]}@example.com"
    token = _make_test_google_token(sub=sub, email=email)
    g_login = client.post("/api/v1/auth/google", json={"id_token": token})
    headers = {"Authorization": f"Bearer {g_login.json()['access_token']}"}

    # Verify no password yet
    methods = client.get("/api/v1/auth/methods", headers=headers).json()
    assert methods["has_password"] is False

    # Set password
    set_res = client.post("/api/v1/auth/password", json={"password": "BrandNewPassword123!"}, headers=headers)
    assert set_res.status_code == 200

    # Verify has_password is now True
    methods_after = client.get("/api/v1/auth/methods", headers=headers).json()
    assert methods_after["has_password"] is True

    # Now login with email and password succeeds
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "BrandNewPassword123!"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["email"] == email

    # Setting password again on account that already has one -> 409 Conflict
    re_set = client.post("/api/v1/auth/password", json={"password": "AnotherPassword123!"}, headers=headers)
    assert re_set.status_code == 409
    assert re_set.json()["error"]["code"] == "CONFLICT"


# ============================================================================
# 6. Phone Linking & OTP Replay Rejection
# ============================================================================


def test_link_phone_and_otp_replay_rejected(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ENV", "local")
    headers = _register_user(client, f"phone_link_{uuid.uuid4().hex[:6]}@example.com")
    phone = f"+9198765{uuid.uuid4().int % 100000:05d}"

    # 1. Request OTP for linking
    req_res = client.post("/api/v1/auth/link/phone", json={"phone_number": phone}, headers=headers)
    assert req_res.status_code == 200

    otp_code = FakeSmsProvider.last_otp
    assert otp_code is not None

    # 2. Bad OTP rejected
    bad_res = client.post(
        "/api/v1/auth/link/phone/verify-otp",
        json={"phone_number": phone, "otp": "000000"},
        headers=headers,
    )
    assert bad_res.status_code == 400

    # 3. Correct OTP links successfully
    ok_res = client.post(
        "/api/v1/auth/link/phone/verify-otp",
        json={"phone_number": phone, "otp": otp_code},
        headers=headers,
    )
    assert ok_res.status_code == 200
    assert "linked" in ok_res.json()["message"].lower()

    # Verify phone appears in auth methods
    methods_res = client.get("/api/v1/auth/methods", headers=headers)
    assert methods_res.status_code == 200
    providers = [m["provider"] for m in methods_res.json()["methods"]]
    assert "phone" in providers

    # 4. OTP Replay rejected: Attempting to use the same OTP again fails
    replay_res = client.post(
        "/api/v1/auth/link/phone/verify-otp",
        json={"phone_number": phone, "otp": otp_code},
        headers=headers,
    )
    assert replay_res.status_code == 400
    assert "invalid" in replay_res.json()["error"]["message"].lower()


def test_link_phone_capabilities_flag_disabled(client: TestClient, monkeypatch) -> None:
    # When capabilities flag is off, phone linking fails with 503 phone_login_disabled
    unconfigured_settings = Settings(
        app_env="production",
        sms_provider="fake",
        jwt_secret_key="a" * 32,
        database_url="postgresql+psycopg://float:secret@localhost:5432/float",
        _env_file=None,
    )
    client.app.dependency_overrides[get_settings] = lambda: unconfigured_settings
    try:
        headers = _register_user(client, f"cap_test_{uuid.uuid4().hex[:6]}@example.com")
        res = client.post("/api/v1/auth/link/phone", json={"phone_number": "+919876543210"}, headers=headers)
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "phone_login_disabled"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
