import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.dependencies import set_llm_gateway
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.answer_models import LLMAnswerOutput
from app.ai.rag.dependencies import set_embedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.core.security import create_access_token


def test_knowledge_endpoint_unauthenticated(client: TestClient) -> None:
    res = client.post("/api/v1/assistant/knowledge", json={"question": "What is the 1930 helpline?"})
    assert res.status_code == 401


def test_knowledge_endpoint_missing_consent(client: TestClient) -> None:
    reg_data = {
        "email": "noconsent_api@example.com",
        "password": "StrongPassword123!",
        "full_name": "No Consent API",
        "terms_accepted": True,
        "ai_data_processing_consent": False,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]

    res = client.post(
        "/api/v1/assistant/knowledge",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is 1930?"},
    )
    assert res.status_code == 403
    data = res.json()
    assert "ai_data_processing" in data["error"]["message"].lower() or "consent" in data["error"]["message"].lower()


def test_knowledge_endpoint_success(client: TestClient) -> None:
    fake_provider = FakeProvider()
    config = LLMConfig(provider="fake", approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake_provider)
    set_llm_gateway(gateway)
    set_embedder(FakeEmbedder())

    reg_data = {
        "email": "knowledge_api_user@example.com",
        "password": "StrongPassword123!",
        "full_name": "Knowledge User",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]

    mock_llm = LLMAnswerOutput(
        status="answered",
        answer="Call helpline 1930 within the golden hour to report unauthorized bank transactions [E1].",
        cited_aliases=["E1"],
    )
    fake_provider.enqueue(json.dumps(mock_llm.model_dump()))

    res = client.post(
        "/api/v1/assistant/knowledge",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What should I do if money is debited fraudulently?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("answered", "insufficient_evidence")
    assert "disclaimer" in data
    assert "trace_id" in data
    assert "confidence" in data


def test_assistant_metrics_requires_auth(client: TestClient) -> None:
    # 1. Unauthenticated -> 401
    res = client.get("/api/v1/assistant/metrics")
    assert res.status_code == 401

    # 2. Invalid internal token -> 401
    res_bad = client.get("/api/v1/assistant/metrics", headers={"X-Internal-Token": "wrong-secret"})
    assert res_bad.status_code == 401

    # 3. Valid internal token -> 200
    settings = client.app.state.settings
    internal_token = settings.internal_metrics_token.get_secret_value()
    res_ok = client.get("/api/v1/assistant/metrics", headers={"X-Internal-Token": internal_token})
    assert res_ok.status_code == 200
    assert "text/plain" in res_ok.headers["content-type"]

    # 4. Regular user Bearer token -> 403 Forbidden
    reg_data = {
        "email": f"reg_user_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "Regular User",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    user_token = reg_res.json()["access_token"]

    res_user = client.get("/api/v1/assistant/metrics", headers={"Authorization": f"Bearer {user_token}"})
    assert res_user.status_code == 403

    # 5. Admin role Bearer token -> 200
    admin_token = create_access_token(str(uuid.uuid4()), claims={"role": "admin"})
    res_admin = client.get("/api/v1/assistant/metrics", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200


def test_assistant_health_liveness_and_details(client: TestClient) -> None:
    fake_provider = FakeProvider()
    config = LLMConfig(provider="fake", approved_for_real_data=True)
    set_llm_gateway(LLMGateway(config=config, adapter=fake_provider))
    set_embedder(FakeEmbedder())

    # 1. Unauthenticated liveness -> 200 (minimal, no topology details)
    res_live = client.get("/api/v1/assistant/health")
    assert res_live.status_code == 200
    live_data = res_live.json()
    assert live_data["status"] == "healthy"
    assert live_data["service"] == "assistant"
    assert "database" not in live_data
    assert "embedder" not in live_data
    assert "gateway" not in live_data

    # 2. Detailed health unauthenticated -> 401
    res_det_unauth = client.get("/api/v1/assistant/health/details")
    assert res_det_unauth.status_code == 401

    # 3. Detailed health regular user -> 403 Forbidden
    reg_data = {
        "email": f"health_reg_user_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "Health User",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    token = reg_res.json()["access_token"]

    res_det_reg = client.get("/api/v1/assistant/health/details", headers={"Authorization": f"Bearer {token}"})
    assert res_det_reg.status_code == 403

    # 4. Detailed health admin role -> 200 with topology
    admin_token = create_access_token(str(uuid.uuid4()), claims={"role": "admin"})
    res_det_admin = client.get("/api/v1/assistant/health/details", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_det_admin.status_code == 200
    det_data = res_det_admin.json()
    assert det_data["status"] in ("healthy", "degraded")
    assert det_data["database"]["status"] == "ok"
    assert det_data["embedder"]["status"] == "ok"
    assert det_data["gateway"]["status"] == "ok"

    # 5. Detailed health internal token -> 200
    settings = client.app.state.settings
    internal_token = settings.internal_metrics_token.get_secret_value()
    res_det_token = client.get(
        "/api/v1/assistant/health/details", headers={"X-Internal-Token": internal_token}
    )
    assert res_det_token.status_code == 200


def test_assistant_purge_requires_confirmation_and_cross_user_isolation(client: TestClient) -> None:
    # Register User A
    user_a = {
        "email": f"user_a_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "User A",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    res_a = client.post("/api/v1/auth/register", json=user_a)
    token_a = res_a.json()["access_token"]

    # Register User B
    user_b = {
        "email": f"user_b_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "User B",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    res_b = client.post("/api/v1/auth/register", json=user_b)
    token_b = res_b.json()["access_token"]

    # 1. Missing confirmation payload -> 422 or 400
    res_no_payload = client.request(
        "DELETE", "/api/v1/assistant/conversations", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert res_no_payload.status_code in (400, 422)

    # 2. Invalid confirmation phrase -> 400
    res_bad_confirm = client.request(
        "DELETE",
        "/api/v1/assistant/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"confirm": True, "confirmation_phrase": "WRONG_PHRASE"},
    )
    assert res_bad_confirm.status_code == 400

    # 3. User A confirms purge
    res_purge_a = client.request(
        "DELETE",
        "/api/v1/assistant/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"confirm": True, "confirmation_phrase": "DELETE_MY_CONVERSATIONS"},
    )
    assert res_purge_a.status_code == 200
    assert res_purge_a.json()["status"] == "purged"

    # 4. User B confirms they can still purge their own independently
    res_purge_b = client.request(
        "DELETE",
        "/api/v1/assistant/conversations",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"confirm": True, "confirmation_phrase": "DELETE_MY_CONVERSATIONS"},
    )
    assert res_purge_b.status_code == 200
    assert res_purge_b.json()["status"] == "purged"

    # 5. Rate limit: User A calling immediately again -> 429
    res_rate_limit = client.request(
        "DELETE",
        "/api/v1/assistant/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"confirm": True, "confirmation_phrase": "DELETE_MY_CONVERSATIONS"},
    )
    assert res_rate_limit.status_code == 429
    assert "rate limit" in res_rate_limit.json()["error"]["message"].lower()


def test_knowledge_degraded_on_retrieval_failed_error(client: TestClient, monkeypatch) -> None:
    """Verify /knowledge catches RetrievalFailedError and returns degraded 200 response, never 500."""
    from app.ai.rag.answer import KnowledgeAnswerService
    from app.ai.rag.retrieval import RetrievalFailedError

    reg_data = {
        "email": f"retrieval_fail_user_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "Retrieval Fail User",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    token = reg_res.json()["access_token"]

    async def mock_answer(*args, **kwargs):
        raise RetrievalFailedError("Both search stages failed: VectorSearchFailed(OperationalError)")

    monkeypatch.setattr(KnowledgeAnswerService, "answer", mock_answer)

    res = client.post(
        "/api/v1/assistant/knowledge",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "I was hacked and lost money in UPI scam"},
    )
    # Must be 200, never 500 or traceback
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "insufficient_evidence"
    assert data["degraded"] is True
    assert "RetrievalFailedError" in data["degraded_reason"] or "Both search stages failed" in data["degraded_reason"]
    assert data["confidence"] == "low"
    assert "1930" in data["answer"]
    assert "temporarily unavailable" in data["answer"].lower()


def test_chat_degraded_when_retrieval_fails(client: TestClient, monkeypatch) -> None:
    """Verify /chat returns degraded response with 'service is temporarily unavailable' and confidence='low'."""
    from app.ai.rag.retrieval import HybridRetriever, RetrievalFailedError

    reg_data = {
        "email": f"chat_fail_user_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "Chat Fail User",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_data)
    token = reg_res.json()["access_token"]

    async def mock_retrieve_fail(*args, **kwargs):
        raise RetrievalFailedError("PostgreSQL connection timeout")

    monkeypatch.setattr(HybridRetriever, "retrieve", mock_retrieve_fail)

    # Route knowledge query so it tries retrieval
    res = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "What is the RBI ombudsman process?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["degraded"] is True
    assert data["confidence"] == "low"
    assert "temporarily unavailable" in data["answer"].lower()
    assert "no data found" not in data["answer"].lower()


def test_readiness_endpoint(client: TestClient) -> None:
    """Verify GET /api/v1/assistant/ready returns structured check results."""
    res = client.get("/api/v1/assistant/ready")
    assert res.status_code in (200, 503)
    data = res.json()
    assert "ready" in data
    assert "checks" in data
    checks = data["checks"]
    assert "vector_extension" in checks
    assert "pg_trgm_extension" in checks
    assert "knowledge_tables_exist" in checks
    assert "published_chunk_count" in checks
    assert "embedder_dimension" in checks


def test_conversation_ownership_rejection_in_chat_and_knowledge(client: TestClient) -> None:
    """Verify nonexistent or foreign conversation_id is rejected with 404 or 403."""
    # User 1
    u1_data = {
        "email": f"u1_conv_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "User One",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    res1 = client.post("/api/v1/auth/register", json=u1_data)
    t1 = res1.json()["access_token"]

    # User 2
    u2_data = {
        "email": f"u2_conv_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "User Two",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    res2 = client.post("/api/v1/auth/register", json=u2_data)
    t2 = res2.json()["access_token"]

    # 1. Nonexistent Swagger placeholder UUID in /chat -> 404
    placeholder_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    res_chat_nonexistent = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {t1}"},
        json={"question": "What is my spending?", "conversation_id": placeholder_id},
    )
    assert res_chat_nonexistent.status_code == 404

    # 2. Nonexistent Swagger placeholder UUID in /knowledge -> 404
    res_know_nonexistent = client.post(
        "/api/v1/assistant/knowledge",
        headers={"Authorization": f"Bearer {t1}"},
        json={"question": "What is 1930?", "conversation_id": placeholder_id},
    )
    assert res_know_nonexistent.status_code == 404

    # 3. Create conversation explicitly owned by User 1 in test session
    import asyncio

    from sqlalchemy import select

    from app.db.session import get_db
    from app.models.conversations import Conversation
    from app.models.user import User as UserModel

    async def _create_u1_conv() -> str:
        override = client.app.dependency_overrides[get_db]
        async for session in override():
            user_stmt = select(UserModel).where(UserModel.email == u1_data["email"])
            u1_user = (await session.execute(user_stmt)).scalar_one()
            conv = Conversation(user_id=u1_user.id, title="User 1 Conversation")
            session.add(conv)
            await session.commit()
            return str(conv.id)
        raise RuntimeError("Could not acquire DB session")

    u1_conv_id = asyncio.run(_create_u1_conv())

    # User 2 attempts to use User 1's conversation_id in /chat -> 403 Forbidden!
    res_chat_cross = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {t2}"},
        json={"question": "What is my spending?", "conversation_id": u1_conv_id},
    )
    assert res_chat_cross.status_code == 403

    # User 2 attempts to use User 1's conversation_id in /knowledge -> 403 Forbidden!
    res_know_cross = client.post(
        "/api/v1/assistant/knowledge",
        headers={"Authorization": f"Bearer {t2}"},
        json={"question": "What is 1930?", "conversation_id": u1_conv_id},
    )
    assert res_know_cross.status_code == 403


def test_assistant_status_with_real_provider_and_401_degraded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify /assistant/status shows real provider/model (no key) and returns degraded on 401 with no traceback."""
    u_data = {
        "email": f"u_status_{uuid.uuid4().hex[:6]}@example.com",
        "password": "StrongPassword123!",
        "full_name": "Status User",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    res_reg = client.post("/api/v1/auth/register", json=u_data)
    token = res_reg.json()["access_token"]

    from pydantic import SecretStr

    from app.ai.gateway.dependencies import get_llm_gateway
    from app.ai.gateway.errors import AuthError

    gw = get_llm_gateway()
    orig_provider = gw.config.provider
    orig_model = gw.config.model
    try:
        gw.config.provider = "groq"
        gw.config.model = "openai/gpt-oss-120b"
        gw.config.api_key = SecretStr("mock-key-not-real")

        # 1. Configured real provider with valid auth
        async def mock_valid_auth() -> bool:
            return True

        monkeypatch.setattr(gw, "validate_auth", mock_valid_auth)

        res_valid = client.get("/api/v1/assistant/status", headers={"Authorization": f"Bearer {token}"})
        assert res_valid.status_code == 200
        body = res_valid.json()
        assert body["status"] == "available"
        assert body["provider"] == "groq"
        assert body["model"] == "openai/gpt-oss-120b"
        assert "mock-key" not in str(body).lower()

        # 2. Key rejected with 401
        async def mock_401_auth() -> bool:
            raise AuthError("Provider authentication error (401)")

        monkeypatch.setattr(gw, "validate_auth", mock_401_auth)

        res_401 = client.get("/api/v1/assistant/status", headers={"Authorization": f"Bearer {token}"})
        assert res_401.status_code == 200
        body_401 = res_401.json()
        assert body_401["status"] == "degraded"
        assert body_401["provider"] == "groq"
        assert body_401["model"] == "openai/gpt-oss-120b"
        assert "traceback" not in str(body_401).lower()
        assert "mock-key" not in str(body_401).lower()
    finally:
        gw.config.provider = orig_provider
        gw.config.model = orig_model

