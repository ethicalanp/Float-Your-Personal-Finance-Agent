from fastapi.testclient import TestClient

from app.core.config import INSECURE_DEV_JWT_SECRET, Settings
from app.main import create_app
from app.services.auth_lockout import AuthLockoutTracker, lockout_tracker


def _register_user(client: TestClient, email: str, password: str = "StrongPass123!") -> str:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Lockout Tester",
            "terms_accepted": True,
            "privacy_accepted": True,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def test_login_progressive_lockout_per_account_generic_response_and_audit(
    client: TestClient,
    monkeypatch,
) -> None:
    email = "lockout_acct@example.com"
    _register_user(client, email)

    # Lower threshold for fast unit test
    monkeypatch.setattr(lockout_tracker, "login_account_threshold", 3)

    # 3 failed attempts trigger lockout; responses must remain generic 401
    for _ in range(3):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword1!"})
        assert r.status_code == 401
        assert r.json()["error"]["message"] == "Invalid email or password."

    # Even with the CORRECT password, account is now locked and returns generic 401
    r_locked = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123!"})
    assert r_locked.status_code == 401
    assert r_locked.json()["error"]["message"] == "Invalid email or password."

    locked, scope = lockout_tracker.is_login_locked(email, "testclient")
    assert locked is True
    assert scope == "account"


def test_login_lockout_per_ip_across_accounts(monkeypatch) -> None:
    tracker = AuthLockoutTracker(login_account_threshold=100, login_ip_threshold=4, base_delay_seconds=30.0)
    for i in range(4):
        tracker.record_login_failure(f"user{i}@example.com", "203.0.113.10")
    locked, scope = tracker.is_login_locked("fresh_user@example.com", "203.0.113.10")
    assert locked is True
    assert scope == "ip"
    # Different IP is not locked
    locked_other, _ = tracker.is_login_locked("fresh_user@example.com", "203.0.113.11")
    assert locked_other is False


def test_password_reset_lockout_and_unlock_via_reset(client: TestClient, monkeypatch) -> None:
    email = "unlock_reset@example.com"
    _register_user(client, email)

    monkeypatch.setattr(lockout_tracker, "login_account_threshold", 2)
    monkeypatch.setattr(lockout_tracker, "reset_account_threshold", 2)

    # Lock the account via bad logins
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword1!"})
    assert lockout_tracker.is_login_locked(email, "testclient")[0] is True

    # Trigger 2 password reset requests -> 3rd should still return generic 200 (rate-limited)
    for _ in range(3):
        r = client.post("/api/v1/auth/password-reset/request", json={"email": email})
        assert r.status_code == 200
        assert r.json()["message"] == "If this email is registered, a password reset link has been sent."

    assert lockout_tracker.is_reset_locked(email, "testclient")[0] is True

    # Simulate reset unlock via confirm flow helper
    lockout_tracker.unlock_via_reset(email)
    assert lockout_tracker.is_login_locked(email, "testclient")[0] is False
    assert lockout_tracker.is_reset_locked(email, "testclient")[0] is False

    # Now login with valid credentials succeeds
    r_ok = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPass123!"})
    assert r_ok.status_code == 200


def test_trusted_host_cors_and_docs_disabled_in_prod() -> None:
    prod_settings = Settings(
        _env_file=None,
        app_env="production",
        debug=False,
        jwt_secret_key="prod-secret-key-at-least-32-characters-long-1234",
        database_url="postgresql+psycopg://user:pass@localhost:5432/float",
        allowed_hosts="api.float.in",
        cors_allowed_origins="https://app.float.in",
        trusted_proxy_hosts="10.0.0.1",
    )
    assert prod_settings.docs_enabled is False
    prod_app = create_app(prod_settings)
    prod_client = TestClient(prod_app, base_url="https://api.float.in")

    # Docs and OpenAPI disabled in production
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404

    # Untrusted Host rejected by TrustedHostMiddleware
    bad_host_res = prod_client.get("/ready", headers={"Host": "evil.example.com"})
    assert bad_host_res.status_code == 400

    # Strict CORS allowlist
    cors_ok = prod_client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://app.float.in", "Access-Control-Request-Method": "POST"},
    )
    assert cors_ok.headers.get("access-control-allow-origin") == "https://app.float.in"

    cors_bad = prod_client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in cors_bad.headers


def test_production_startup_refuses_default_or_missing_secrets() -> None:
    import pytest

    with pytest.raises(ValueError, match="PFA_JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            jwt_secret_key=INSECURE_DEV_JWT_SECRET,
            database_url="postgresql+psycopg://user:pass@localhost:5432/float",
        )

    with pytest.raises(ValueError, match="PFA_ALLOWED_HOSTS"):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            jwt_secret_key="prod-secret-key-at-least-32-characters-long-1234",
            database_url="postgresql+psycopg://user:pass@localhost:5432/float",
            allowed_hosts="*",
        )

    with pytest.raises(ValueError, match="PFA_CORS_ALLOWED_ORIGINS"):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            jwt_secret_key="prod-secret-key-at-least-32-characters-long-1234",
            database_url="postgresql+psycopg://user:pass@localhost:5432/float",
            cors_allowed_origins="*",
        )

    with pytest.raises(ValueError, match="PFA_ADMIN_SESSION_SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            jwt_secret_key="prod-secret-key-at-least-32-characters-long-1234",
            database_url="postgresql+psycopg://user:pass@localhost:5432/float",
            admin_enabled=True,
            admin_session_secret_key=None,
        )
