from fastapi.testclient import TestClient

from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.dependencies import set_llm_gateway
from app.ai.gateway.manager import LLMGateway


def test_assistant_status_unauthenticated(client: TestClient) -> None:
    response = client.get("/api/v1/assistant/status")
    # Unauthenticated request must be rejected
    assert response.status_code == 401


def test_assistant_status_authenticated(client: TestClient) -> None:
    fake_adapter = FakeProvider()
    config = LLMConfig(
        provider="groq",
        model="llama-3.3-70b-versatile",
        approved_for_real_data=True,
    )
    gateway = LLMGateway(config=config, adapter=fake_adapter)
    set_llm_gateway(gateway)

    # Register test user
    reg_data = {
        "email": "assistant_status@example.com",
        "password": "StrongPassword123!",
        "full_name": "Assistant Tester",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]

    response = client.get(
        "/api/v1/assistant/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "available"
    assert data["provider"] == "groq"
    assert data["model"] == "llama-3.3-70b-versatile"
    assert data["approved_for_real_data"] is True
    assert data["circuit_state"] == "CLOSED"

    # Verify zero secret keys or credentials in response
    response_text = response.text
    assert "api_key" not in response_text
    assert "secret" not in response_text
