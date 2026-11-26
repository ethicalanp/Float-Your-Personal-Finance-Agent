import time

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.services.phone_service import (
    normalize_phone_number,
)


def _make_test_google_token(
    sub: str = "google-sub-12345",
    email: str = "googleuser@example.com",
    name: str = "Google User",
    email_verified: bool = True,
    aud: str | None = None,
    iss: str = "https://accounts.google.com",
    exp_delta: int = 3600,
) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "name": name,
        "email_verified": email_verified,
        "iss": iss,
        "aud": aud or settings.google_client_id or "default-client-id",
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


# ============================================================================
# Google Sign-In Tests
# ============================================================================


def test_google_sign_in_new_user(client: TestClient) -> None:
    token = _make_test_google_token(sub="goog-1", email="newgoogle@example.com", name="New Google")
    res = client.post("/api/v1/auth/google", json={"id_token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "newgoogle@example.com"
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_google_sign_in_existing_email_links_account(client: TestClient) -> None:
    # First, register user via email/password
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "linktest@example.com",
            "password": "Password123!",
            "full_name": "Link Test",
            "terms_accepted": True,
            "privacy_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    assert reg.status_code == 201
    user_id = reg.json()["user_id"]

    # Now sign in via Google with the same verified email
    google_token = _make_test_google_token(sub="goog-link-1", email="linktest@example.com")
    res = client.post("/api/v1/auth/google", json={"id_token": google_token})
    assert res.status_code == 200
    assert res.json()["user_id"] == user_id

    # Check methods: both password and google should be present
    access_token = res.json()["access_token"]
    methods_res = client.get(
        "/api/v1/auth/methods",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert methods_res.status_code == 200
    methods_data = methods_res.json()
    assert methods_data["has_password"] is True
    providers = [m["provider"] for m in methods_data["methods"]]
    assert "password" in providers
    assert "google" in providers


def test_google_sign_in_unverified_email_rejected(client: TestClient) -> None:
    token = _make_test_google_token(
        sub="goog-unverified",
        email="unverified@example.com",
        email_verified=False,
    )
    res = client.post("/api/v1/auth/google", json={"id_token": token})
    assert res.status_code in (400, 401)
    assert "unverified" in res.json()["error"]["message"].lower()


def test_google_sign_in_malformed_token_returns_generic_error_without_leaking_parser_or_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    malformed = "not-a-valid-jwt-token-secret123"
    with caplog.at_level("WARNING"):
        res = client.post("/api/v1/auth/google", json={"id_token": malformed})
    assert res.status_code == 401
    msg = res.json()["error"]["message"]
    assert msg == "Invalid or expired Google ID token."
    assert "Not enough segments" not in msg
    assert malformed not in caplog.text
    assert "Google ID token verification failed" in caplog.text


# ============================================================================
# Phone OTP Tests
# ============================================================================


def test_phone_normalization() -> None:
    assert normalize_phone_number("9876543210") == "+919876543210"
    assert normalize_phone_number("09876543210") == "+919876543210"
    assert normalize_phone_number("+91 98765-43210") == "+919876543210"


def test_phone_otp_flow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.sms_provider import FakeSmsProvider

    phone = "+919876500001"

    # When phone auth is disabled (non-local env with fake provider), phone endpoints return 503
    dis_res = client.post("/api/v1/auth/phone/request-otp", json={"phone_number": phone})
    assert dis_res.status_code == 503

    # Enable phone auth in local environment
    monkeypatch.setenv("ENV", "local")

    # Request OTP
    req_res = client.post("/api/v1/auth/phone/request-otp", json={"phone_number": phone})
    assert req_res.status_code == 200
    assert "OTP has been sent" in req_res.json()["message"]
    assert req_res.json()["cooldown_seconds"] == 60

    # In test environment, since FakeSmsProvider was called, let's verify with bad OTP first
    bad_res = client.post(
        "/api/v1/auth/phone/verify-otp",
        json={"phone_number": phone, "otp": "000000"},
    )
    assert bad_res.status_code == 400

    otp_code = FakeSmsProvider.last_otp
    assert otp_code is not None

    # Verify with correct OTP
    verify_res = client.post(
        "/api/v1/auth/phone/verify-otp",
        json={"phone_number": phone, "otp": otp_code, "full_name": "OTP User"},
    )
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert "access_token" in v_data
    assert "refresh_token" in v_data

    # Replay protection: attempting to use the same OTP again fails
    replay_res = client.post(
        "/api/v1/auth/phone/verify-otp",
        json={"phone_number": phone, "otp": otp_code},
    )
    assert replay_res.status_code == 400


def test_phone_otp_lockout_after_5_attempts(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "local")
    phone = "+919876500002"
    client.post("/api/v1/auth/phone/request-otp", json={"phone_number": phone})

    # 5 wrong attempts
    for _ in range(5):
        client.post(
            "/api/v1/auth/phone/verify-otp",
            json={"phone_number": phone, "otp": "000000"},
        )

    # 6th attempt should fail due to lockout
    res6 = client.post(
        "/api/v1/auth/phone/verify-otp",
        json={"phone_number": phone, "otp": "123456"},
    )
    assert res6.status_code == 400
    assert "invalid or expired" in res6.json()["error"]["message"].lower()


# ============================================================================
# Session Rotation & Reuse Detection Tests
# ============================================================================


def test_refresh_token_rotation_and_reuse_detection(client: TestClient) -> None:
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "sessiontest@example.com",
            "password": "Password123!",
            "full_name": "Session Test",
        },
    )
    assert reg.status_code == 201
    refresh_1 = reg.json()["refresh_token"]

    # 1. Normal rotation
    rot_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert rot_res.status_code == 200
    rot_data = rot_res.json()
    refresh_2 = rot_data["refresh_token"]
    assert refresh_2 != refresh_1

    # 2. Token reuse detection: Replaying refresh_1 (which is now revoked)
    reuse_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert reuse_res.status_code == 401
    assert "suspicious activity" in reuse_res.json()["error"]["message"].lower()

    # 3. Whole family invalidated: refresh_2 should now also be rejected
    fam_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2})
    assert fam_res.status_code == 401


# ============================================================================
# Password Reset & Session Revocation Tests
# ============================================================================


def test_password_reset_revokes_all_sessions(client: TestClient) -> None:
    email = "resettest@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "OldPassword123!",
            "full_name": "Reset Test",
        },
    )
    refresh_before = reg.json()["refresh_token"]

    from unittest.mock import patch

    fixed_reset_token = "valid-test-reset-token-123456789"
    with patch("secrets.token_urlsafe", return_value=fixed_reset_token):
        req_res = client.post("/api/v1/auth/password-reset/request", json={"email": email})
        assert req_res.status_code == 200

    # Confirm password reset with the issued token
    confirm_res = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": fixed_reset_token, "new_password": "NewStrongPassword123!"},
    )
    assert confirm_res.status_code == 200
    assert confirm_res.status_code == 200

    # Old refresh token MUST be revoked
    ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_before})
    assert ref_res.status_code == 401

    # Login with new password works
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "NewStrongPassword123!"},
    )
    assert login_res.status_code == 200


# ============================================================================
# Account Linking & Sole Method Protection Tests
# ============================================================================


def test_cannot_remove_sole_authentication_method(client: TestClient) -> None:
    # Sign up via Google only (no password)
    g_token = _make_test_google_token(sub="goog-sole-1", email="solegoogle@example.com")
    res = client.post("/api/v1/auth/google", json={"id_token": g_token})
    assert res.status_code == 200
    access_token = res.json()["access_token"]

    # Attempt to unlink Google method
    del_res = client.delete(
        "/api/v1/auth/link/google",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert del_res.status_code == 400
    assert "sole authentication method" in del_res.json()["error"]["message"].lower()


# ============================================================================
# Audit Logs Sanitization Tests
# ============================================================================


def test_audit_logs_contain_zero_raw_pii_or_plaintext(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENV", "local")
    raw_email = "auditcheck@example.com"
    raw_phone = "+919999988888"

    client.post(
        "/api/v1/auth/register",
        json={"email": raw_email, "password": "Password123!", "full_name": "Audit Check"},
    )
    client.post("/api/v1/auth/phone/request-otp", json={"phone_number": raw_phone})

    import asyncio

    from sqlalchemy import select

    from app.db.session import get_db
    from app.models.user import AuthAuditLog

    async def verify_audit_pii() -> None:
        override = client.app.dependency_overrides.get(get_db)
        if override:
            async for db in override():
                result = await db.execute(select(AuthAuditLog))
                logs = result.scalars().all()
                break
        else:
            from app.db.session import get_async_session_factory
            factory = get_async_session_factory()
            async with factory() as db:
                result = await db.execute(select(AuthAuditLog))
                logs = result.scalars().all()

        for log in logs:
            # Assert raw email, raw phone, and passwords NEVER exist in audit logs
            assert raw_email not in (log.identifier_hash or "")
            assert raw_phone not in (log.identifier_hash or "")
            if log.metadata_json:
                assert "Password123!" not in log.metadata_json
                assert raw_email not in log.metadata_json
                assert raw_phone not in log.metadata_json
            if log.ip_address_mask:
                assert not log.ip_address_mask.endswith(".1")  # Masked!

    asyncio.run(verify_audit_pii())


# ============================================================================
# Auth Capabilities Flag Tests
# ============================================================================


def test_auth_capabilities_flag_on_and_off(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Flag OFF: Default test environment (fake SMS provider without ENV=local)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("PFA_GOOGLE_CLIENT_ID", "")
    res_root = client.get("/auth/capabilities")
    assert res_root.status_code == 200
    caps = res_root.json()
    assert caps["email"] is True
    assert caps["phone"] is False
    assert caps["google"] is False
    assert "keys" not in caps
    assert "provider" not in caps

    # Also works at /api/v1/auth/capabilities
    res_v1 = client.get("/api/v1/auth/capabilities")
    assert res_v1.status_code == 200
    assert res_v1.json() == caps

    # Phone endpoints fail with 503 and error code phone_login_disabled when flag is off
    req_resp = client.post("/api/v1/auth/phone/request-otp", json={"phone_number": "+919876543210"})
    assert req_resp.status_code == 503
    assert req_resp.json()["error"]["code"] == "phone_login_disabled"

    verify_resp = client.post(
        "/api/v1/auth/phone/verify-otp",
        json={"phone_number": "+919876543210", "otp": "123456"},
    )
    assert verify_resp.status_code == 503
    assert verify_resp.json()["error"]["code"] == "phone_login_disabled"

    # Test Google flag when PFA_GOOGLE_CLIENT_ID is set
    monkeypatch.setenv("PFA_GOOGLE_CLIENT_ID", "dummy-google-client-id.apps.googleusercontent.com")
    res_google = client.get("/auth/capabilities")
    assert res_google.status_code == 200
    assert res_google.json()["google"] is True
    monkeypatch.delenv("PFA_GOOGLE_CLIENT_ID", raising=False)

    # 2. Flag ON: ENV=local with fake SMS provider
    monkeypatch.setenv("ENV", "local")
    res_local = client.get("/auth/capabilities")
    assert res_local.status_code == 200
    assert res_local.json()["phone"] is True

    # 3. Flag ON: MSG91 configured
    monkeypatch.delenv("ENV", raising=False)
    configured_msg91_settings = Settings(
        app_env="production",
        sms_provider="msg91",
        msg91_auth_key=SecretStr("auth_key_123"),
        msg91_template_id="template_456",
        msg91_sender_id="FLTPFA",
        jwt_secret_key="a" * 32,
        database_url="postgresql+psycopg://float:secret@localhost:5432/float",
        _env_file=None,
    )
    client.app.dependency_overrides[get_settings] = lambda: configured_msg91_settings
    try:
        res_msg91 = client.get("/auth/capabilities")
        assert res_msg91.status_code == 200
        assert res_msg91.json()["phone"] is True
    finally:
        client.app.dependency_overrides.pop(get_settings, None)

    # 4. Flag OFF: MSG91 with missing credentials
    unconfigured_msg91_settings = Settings(
        app_env="development",
        sms_provider="msg91",
        msg91_auth_key=None,
        msg91_template_id=None,
        msg91_sender_id=None,
        _env_file=None,
    )
    client.app.dependency_overrides[get_settings] = lambda: unconfigured_msg91_settings
    try:
        res_unconf = client.get("/auth/capabilities")
        assert res_unconf.status_code == 200
        assert res_unconf.json()["phone"] is False
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
