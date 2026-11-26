import logging
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.models.enums import AuthAuditEventType
from app.models.user import AuthAuditLog
from app.services.phone_service import hash_identifier
from app.services.sms_provider import Msg91SmsProvider


def _get_msg91_settings(
    sms_provider: str = "msg91",
    auth_key: str | None = "dummy_auth_key_123",
    template_id: str | None = "dummy_template_456",
    sender_id: str | None = "FLTPFA",
    sms_daily_cap: int = 1000,
    app_env: str = "development",
) -> Settings:
    return Settings(
        app_env=app_env,  # type: ignore[arg-type]
        sms_provider=sms_provider,  # type: ignore[arg-type]
        msg91_auth_key=SecretStr(auth_key) if auth_key else None,
        msg91_template_id=template_id,
        msg91_sender_id=sender_id,
        sms_daily_cap=sms_daily_cap,
        _env_file=None,
    )


# ============================================================================
# 1. Success test
# ============================================================================


@pytest.mark.asyncio
async def test_msg91_success(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    phone = "+919876543210"
    otp = "889977"
    ident_hash = hash_identifier(phone)

    request_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_calls.append(request)
        return httpx.Response(200, json={"message": "OTP sent", "type": "success", "request_id": "msg91_req_789"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = _get_msg91_settings()
        provider = Msg91SmsProvider(settings=settings, http_client=http_client)

        success = await provider.send_otp(phone, otp)
        assert success is True

    assert len(request_calls) == 1
    req = request_calls[0]
    assert req.headers["authkey"] == "dummy_auth_key_123"
    assert req.url.params["template_id"] == "dummy_template_456"
    assert req.url.params["mobile"] == "919876543210"
    assert req.url.params["sender"] == "FLTPFA"

    # Security assertion: SMS provider logger never logs raw phone numbers or OTPs
    provider_records = [r for r in caplog.records if r.name == "app.services.sms_provider"]
    assert len(provider_records) > 0
    for record in provider_records:
        msg = record.getMessage()
        assert phone not in msg
        assert otp not in msg

    # Assert hashed phone and message id are logged
    assert ident_hash in caplog.text
    assert "msg91_req_789" in caplog.text


# ============================================================================
# 2. 4xx Client Error (no retry)
# ============================================================================


@pytest.mark.asyncio
async def test_msg91_4xx_no_retry(caplog: pytest.LogCaptureFixture) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"message": "Invalid Auth Key", "type": "error"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = _get_msg91_settings()
        provider = Msg91SmsProvider(settings=settings, http_client=http_client)

        success = await provider.send_otp("+919876543210", "123456")
        assert success is False

    # Bounded retry rule: 4xx errors MUST NOT be retried
    assert call_count == 1
    assert "no retry" in caplog.text


# ============================================================================
# 3. 5xx Server Error then Success (bounded retries)
# ============================================================================


@pytest.mark.asyncio
async def test_msg91_5xx_then_success() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(200, json={"type": "success", "request_id": "retry_ok_123"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = _get_msg91_settings()
        provider = Msg91SmsProvider(settings=settings, http_client=http_client)

        success = await provider.send_otp("+919876543210", "123456")
        assert success is True

    # Attempt 1 failed with 502, Attempt 2 succeeded with 200
    assert call_count == 2


# ============================================================================
# 4. Timeout Exhaustion
# ============================================================================


@pytest.mark.asyncio
async def test_msg91_timeout_exhaustion(caplog: pytest.LogCaptureFixture) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("Connection timed out", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        settings = _get_msg91_settings()
        provider = Msg91SmsProvider(settings=settings, http_client=http_client)

        success = await provider.send_otp("+919876543210", "123456")
        assert success is False

    # Bounded retries: 3 attempts (initial + 2 retries)
    assert call_count == 3
    assert "exhausted 3 attempts" in caplog.text


# ============================================================================
# 5. Daily Cap Hit Before Provider Call
# ============================================================================


def test_daily_cap_hit_before_provider_call(client: TestClient) -> None:
    phone1 = "+919876543291"
    phone2 = "+919876543292"
    ident_hash2 = hash_identifier(phone2)

    # Set daily cap to 1
    cap_settings = _get_msg91_settings(sms_daily_cap=1)
    client.app.dependency_overrides[get_settings] = lambda: cap_settings
    try:
        # First request consumes the daily cap quota of 1
        res1 = client.post("/api/v1/auth/phone/request-otp", json={"phone_number": phone1})
        assert res1.status_code == 200

        # Second request hits the daily cap before calling provider
        with patch("app.services.sms_provider.Msg91SmsProvider.send_otp") as mock_send:
            res2 = client.post("/api/v1/auth/phone/request-otp", json={"phone_number": phone2})
            assert res2.status_code == 200
            assert "OTP has been sent" in res2.json()["message"]

            # Provider MUST NOT be called when daily cap is reached
            mock_send.assert_not_called()
    finally:
        client.app.dependency_overrides.pop(get_settings, None)

    # Verify audit event for daily cap exceeded was recorded
    import asyncio

    from app.core.dependencies import get_db

    async def verify_audit() -> None:
        from sqlalchemy import select

        override = client.app.dependency_overrides.get(get_db)
        if override:
            async for db in override():
                stmt = select(AuthAuditLog).where(
                    AuthAuditLog.identifier_hash == ident_hash2,
                    AuthAuditLog.event_type == AuthAuditEventType.OTP_REQUEST,
                )
                res = await db.execute(stmt)
                logs = res.scalars().all()
                assert any("daily_cap_exceeded" in (log.metadata_json or "") for log in logs)
                break

    asyncio.run(verify_audit())


# ============================================================================
# 6. Misconfigured Env & Fail Closed
# ============================================================================


def test_misconfigured_env_fails_closed(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    # 1. Startup validation in non-development environment rejects incomplete MSG91 configuration
    with pytest.raises(ValueError, match="PFA_MSG91_AUTH_KEY, PFA_MSG91_TEMPLATE_ID, and PFA_MSG91_SENDER_ID"):
        Settings(
            app_env="production",
            sms_provider="msg91",
            msg91_auth_key=None,
            jwt_secret_key="a" * 32,
            database_url="postgresql+psycopg://float:secret@localhost:5432/float",
            _env_file=None,
        )

    # 2. Provider is_configured() returns False and send_otp() fails closed without logging OTP
    unconfigured_settings = Settings(
        app_env="development",
        sms_provider="msg91",
        msg91_auth_key=None,
        msg91_template_id=None,
        msg91_sender_id=None,
        _env_file=None,
    )
    unconfigured_provider = Msg91SmsProvider(settings=unconfigured_settings)
    assert unconfigured_provider.is_configured() is False

    import asyncio

    res = asyncio.run(unconfigured_provider.send_otp("+919876543210", "123456"))
    assert res is False

    # 2b. Fake provider does not log raw phone or OTP outside ENV=local
    from app.services.sms_provider import FakeSmsProvider

    fake_provider = FakeSmsProvider()
    caplog.clear()
    asyncio.run(fake_provider.send_otp("+919876543210", "123456"))
    assert "+919876543210" not in caplog.text
    assert "123456" not in caplog.text

    # 3. /ready endpoint reports 503 Service Unavailable when MSG91 is misconfigured
    client.app.dependency_overrides[get_settings] = lambda: unconfigured_settings
    try:
        ready_res = client.get("/ready")
        assert ready_res.status_code == 503
        data = ready_res.json()
        assert data["ready"] is False
        assert data["checks"]["sms_provider"] == "misconfigured"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)

    # 3b. /ready endpoint reports 503 when fake provider is set in production
    prod_fake_settings = Settings.model_construct(
        app_env="production",
        sms_provider="fake",
        jwt_secret_key="a" * 32,
        database_url="postgresql+psycopg://float:secret@localhost:5432/float",
    )
    client.app.dependency_overrides[get_settings] = lambda: prod_fake_settings
    try:
        ready_res = client.get("/ready")
        assert ready_res.status_code == 503
        data = ready_res.json()
        assert data["ready"] is False
        assert data["checks"]["sms_provider"] == "misconfigured"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
