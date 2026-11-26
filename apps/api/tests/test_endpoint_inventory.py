import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

app = create_app()
schema = app.openapi()


def get_all_routes() -> list[dict[str, Any]]:
    paths = schema.get("paths", {})
    routes = []
    for path, methods in paths.items():
        for method, spec in methods.items():
            if method.lower() in ("get", "post", "put", "patch", "delete"):
                routes.append({
                    "path": path,
                    "method": method.upper(),
                    "secured": bool(spec.get("security", [])),
                    "tags": spec.get("tags", []),
                    "params": spec.get("parameters", []),
                    "request_body": spec.get("requestBody"),
                })
    return routes


ALL_ROUTES = get_all_routes()
SECURED_ROUTES = [r for r in ALL_ROUTES if r["secured"]]
PUBLIC_ROUTES = [r for r in ALL_ROUTES if not r["secured"]]


def _sample_path(path_template: str) -> str:
    """Replace path parameters with valid mock UUIDs."""
    res = path_template
    for param in ["notification_id", "draft_id", "trace_id", "case_id", "commitment_id"]:
        res = res.replace(f"{{{param}}}", str(uuid.uuid4()))
    return res


@pytest.fixture
def user_a_client(client: TestClient) -> tuple[TestClient, dict[str, str], str]:
    email = f"user_a_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "User A",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    user_id = reg.json()["user_id"]
    return client, {"Authorization": f"Bearer {token}"}, user_id


@pytest.fixture
def user_b_client(client: TestClient) -> tuple[TestClient, dict[str, str], str]:
    email = f"user_b_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "User B",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    user_id = reg.json()["user_id"]
    return client, {"Authorization": f"Bearer {token}"}, user_id


def test_public_endpoints_accessible_without_auth(client: TestClient) -> None:
    """Assert all public routes do not require Bearer token."""
    internal_token_paths = {
        "/api/v1/assistant/metrics",
        "/api/v1/assistant/health/details",
    }
    for r in PUBLIC_ROUTES:
        method = r["method"]
        path = r["path"]
        if method == "GET":
            res = client.get(path)
            if path in internal_token_paths:
                assert res.status_code in (401, 403), f"Internal endpoint {path} should require internal token"
            else:
                assert res.status_code in (200, 503), f"Public endpoint {path} failed: {res.status_code}"


def test_secured_endpoints_reject_missing_token(client: TestClient) -> None:
    """Assert every secured route rejects requests lacking an Authorization header with 401 or 403."""
    for r in SECURED_ROUTES:
        method = r["method"]
        path = _sample_path(r["path"])
        req_fn = getattr(client, method.lower())
        res = req_fn(path)
        assert res.status_code in (401, 403), (
            f"Secured route {method} {path} did not reject missing token (status: {res.status_code})"
        )
        data = res.json()
        assert "error" in data, f"Missing unified error shape in {method} {path}: {data}"
        assert "code" in data["error"]
        assert "message" in data["error"]


def test_secured_endpoints_reject_invalid_token(client: TestClient) -> None:
    """Assert every secured route rejects malformed/invalid Bearer token with 401."""
    headers = {"Authorization": "Bearer invalid.garbage.token"}
    for r in SECURED_ROUTES:
        method = r["method"]
        path = _sample_path(r["path"])
        req_fn = getattr(client, method.lower())
        res = req_fn(path, headers=headers)
        assert res.status_code == 401, (
            f"Secured route {method} {path} did not return 401 on invalid token (got {res.status_code})"
        )
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] in ("UNAUTHORIZED", "INVALID_TOKEN")


def test_user_owned_resources_reject_cross_tenant_access(
    user_a_client: tuple[TestClient, dict[str, str], str],
    user_b_client: tuple[TestClient, dict[str, str], str],
) -> None:
    """Assert user B cannot access or mutate resources owned by user A."""
    client_a, headers_a, user_a_id = user_a_client
    client_b, headers_b, user_b_id = user_b_client

    # 1. User A creates an account
    acc_res = client_a.post(
        "/api/v1/plan/accounts",
        headers=headers_a,
        json={
            "name": "User A Private Account",
            "account_type": "savings",
            "institution_name": "Axis Bank",
            "account_number_mask": "****9999",
            "currency": "INR",
            "initial_balance": 10000.0,
        },
    )
    assert acc_res.status_code == 201
    account_id = acc_res.json()["id"]

    # User B lists accounts - must not see User A's account
    b_accounts = client_b.get("/api/v1/plan/accounts", headers=headers_b).json()
    assert not any(a["id"] == account_id for a in b_accounts)

    # User B attempts to upload statement into User A's account - must reject with 404
    b_upload = client_b.post(
        "/api/v1/plan/upload-statement",
        headers=headers_b,
        json={
            "account_id": account_id,
            "format": "csv",
            "content": "Date,Description,Debit,Credit\n2026-03-01,Attack Txn,5000,0",
        },
    )
    assert b_upload.status_code == 404
    assert b_upload.json()["error"]["code"] == "NOT_FOUND"

    # 2. User A creates a recovery case
    case_res = client_a.post(
        "/api/v1/protect/recovery-cases",
        headers=headers_a,
        json={
            "scam_type": "upi_fraud",
            "amount_lost": 25000.0,
            "platform": "WhatsApp",
            "incident_summary": "User A unauthorized UPI debit occurred after clicking link",
        },
    )
    assert case_res.status_code == 201
    case_id = case_res.json().get("case_id") or case_res.json().get("id")

    # User B attempts to patch User A's recovery case - must reject with 404
    b_patch = client_b.patch(
        f"/api/v1/protect/recovery-cases/{case_id}",
        headers=headers_b,
        json={"status": "resolved", "notes": "Hacked by User B"},
    )
    assert b_patch.status_code == 404
    assert b_patch.json()["error"]["code"] == "NOT_FOUND"


def test_invalid_payload_bodies_return_standard_error_never_500(
    user_a_client: tuple[TestClient, dict[str, str], str],
) -> None:
    """Assert endpoints receiving malformed request bodies return 422 with VALIDATION_ERROR and never 500."""
    client, headers, _ = user_a_client

    test_payloads = [
        ("POST", "/api/v1/plan/accounts", {"invalid_field": 123}),
        ("POST", "/api/v1/plan/upload-statement", {"account_id": "not-a-uuid"}),
        ("POST", "/api/v1/protect/check", {"missing_content": True}),
        ("POST", "/api/v1/protect/recovery-cases", {"amount_lost": "not-a-number"}),
        ("POST", "/api/v1/assistant/chat", {"bad_message": 999}),
        ("POST", "/api/v1/assistant/knowledge", {}),
    ]

    for method, path, body in test_payloads:
        req_fn = getattr(client, method.lower())
        res = req_fn(path, headers=headers, json=body)
        assert res.status_code == 422, f"{method} {path} returned {res.status_code} instead of 422 on invalid body"
        data = res.json()
        assert "error" in data, f"{method} {path} did not return standard error format: {data}"
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert len(data["error"]["details"]) > 0
