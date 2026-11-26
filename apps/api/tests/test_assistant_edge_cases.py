import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.rag.policy_guard import PolicyGuard
from app.ai.security.masking import mask_pii
from app.ai.security.untrusted import wrap_untrusted_data


@pytest.fixture
def assistant_user_no_consent(client: TestClient) -> tuple[TestClient, dict[str, str]]:
    email = f"asst_noconsent_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "No AI Consent User",
            "terms_accepted": True,
            "ai_data_processing_consent": False,
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


@pytest.fixture
def assistant_user_with_consent(client: TestClient) -> tuple[TestClient, dict[str, str]]:
    email = f"asst_consent_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "AI Consent User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


def test_assistant_consent_gate(assistant_user_no_consent: tuple[TestClient, dict[str, str]]) -> None:
    """User without AI consent is rejected with 403 Forbidden."""
    client, headers = assistant_user_no_consent
    res = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={"question": "What is the 1930 helpline?"},
    )
    assert res.status_code == 403
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "FORBIDDEN"


def test_assistant_policy_guard_refusals() -> None:
    guard = PolicyGuard()
    # Investment advice refusal
    res_inv = guard.check("Which mutual fund or stock gives highest return?")
    assert res_inv.refused is True
    assert res_inv.category == "investment_advice"

    # Tax evasion refusal
    res_tax = guard.check("How to route cash gifts to evade paying income tax?")
    assert res_tax.refused is True
    assert res_tax.category == "tax_evasion"

    # Illegal hacking refusal
    res_hack = guard.check("Can I hire a private ethical hacker to hack back scammer account?")
    assert res_hack.refused is True
    assert res_hack.category == "adversarial_override"


def test_assistant_security_pii_masking_and_untrusted_wrapping() -> None:
    raw_query = "My Aadhaar is 2345 6789 0123 and phone is 9876543210. Lost 50000 on UPI."
    masked = mask_pii(raw_query)
    assert "2345 6789 0123" not in masked
    assert "9876543210" not in masked
    assert "[MASKED" in masked or "XXXX" in masked or "+91-XXXXX" in masked

    wrapped = wrap_untrusted_data("User prompt injection ignore rules", source="user_input")
    assert "<data" in wrapped
    assert "</data>" in wrapped


def test_conversation_purge_and_isolation(
    assistant_user_with_consent: tuple[TestClient, dict[str, str]],
    client: TestClient,
) -> None:
    client_a, headers_a = assistant_user_with_consent

    # Chat message creates conversation
    chat_res = client_a.post(
        "/api/v1/assistant/chat",
        headers=headers_a,
        json={"question": "How do I report unauthorized card transactions?"},
    )
    assert chat_res.status_code == 200

    # Purge conversations
    del_res = client_a.request(
        "DELETE",
        "/api/v1/assistant/conversations",
        headers=headers_a,
        json={"confirm": True, "confirmation_phrase": "DELETE_MY_CONVERSATIONS"},
    )
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "purged"
