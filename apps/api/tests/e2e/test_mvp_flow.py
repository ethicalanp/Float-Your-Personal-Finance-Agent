import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.agent.dependencies import set_orchestrator
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.dependencies import set_llm_gateway
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.answer_models import LLMAnswerOutput
from app.ai.rag.dependencies import set_embedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.core.config import Settings
from app.db.session import get_db, to_sync_database_url
from app.main import create_app
from app.models.enums import AccountType
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

POSTGRES_TEST_URL = os.environ.get(
    "POSTGRES_TEST_URL",
    os.environ.get("PFA_DATABASE_URL", "postgresql+psycopg://float:float_dev_password_change_me@localhost:5432/float_ci"),
)


def _check_postgres_connection() -> bool:
    if "sqlite" in POSTGRES_TEST_URL.lower():
        return False
    try:
        from sqlalchemy import create_engine

        sync_url = to_sync_database_url(POSTGRES_TEST_URL)
        engine = create_engine(sync_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        engine.dispose()
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _check_postgres_connection()


@pytest.fixture
def mvp_client(client: TestClient) -> TestClient:
    """Fixture providing a test client with fake LLM/embedder and DB configured."""
    fake_provider = FakeProvider()
    config = LLMConfig(provider="fake", approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake_provider)
    set_llm_gateway(gateway)
    embedder = FakeEmbedder()
    set_embedder(embedder)
    set_orchestrator(None)

    if not POSTGRES_AVAILABLE:
        return client

    # When Postgres is available, construct an app connected to the Postgres test database
    settings = Settings(
        app_env="test",
        database_url=POSTGRES_TEST_URL,
        jwt_secret_key="mvp-e2e-test-secret-key-minimum-32-chars-long",
        internal_metrics_token="test-internal-metrics-token",
        _env_file=None,
    )
    application = create_app(settings)
    engine = create_async_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed published knowledge document and chunk for grounded Q&A with citations
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        sync_engine = create_engine(to_sync_database_url(POSTGRES_TEST_URL))
        with Session(sync_engine) as sync_db:
            doc_id = uuid.uuid4()
            chunk_id = uuid.uuid4()
            doc = KnowledgeDocument(
                id=doc_id,
                title="Cyber Crime Helpline 1930 Guidelines",
                publisher="I4C / MHA",
                source_url="https://cybercrime.gov.in/1930",
                language="en",
                doc_type="advisory",
                version="1.0",
                status="published",
                licence_note="Government Open Data",
            )
            chunk = KnowledgeChunk(
                id=chunk_id,
                document_id=doc_id,
                chunk_index=0,
                content=(
                    "Victims of cyber fraud must call national helpline 1930 immediately "
                    "within the golden hour to freeze fraudulent transactions."
                ),
                token_count=20,
                embedding_model="fake-embedder",
                embedding_dim=768,
                embedding=[0.1] * 768,
                language="en",
                is_indexable=True,
            )
            sync_db.add_all([doc, chunk])
            sync_db.commit()
        sync_engine.dispose()
    except Exception:
        pass

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    application.dependency_overrides[get_db] = override_get_db
    return TestClient(application)


def test_mvp_end_to_end_flow(mvp_client: TestClient) -> None:
    """Complete end-to-end MVP user flow exercising all primary subsystems."""
    unique_id = uuid.uuid4().hex[:8]
    email = f"mvp_flow_{unique_id}@example.com"
    password = "StrongPassword123!"

    # 1. Register User
    reg_payload = {
        "email": email,
        "password": password,
        "full_name": "MVP Tester",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
        "consent_version": "v1.0",
    }
    reg_resp = mvp_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_resp.status_code == 201, reg_resp.text
    auth_data = reg_resp.json()
    assert "access_token" in auth_data
    token = auth_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Login User
    login_resp = mvp_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert login_resp.json()["access_token"] is not None

    # 3. Verify / Update Consent
    consent_resp = mvp_client.post(
        "/api/v1/auth/consent",
        headers=headers,
        json={
            "terms_accepted": True,
            "ai_data_processing_consent": True,
            "consent_version": "v1.0",
        },
    )
    assert consent_resp.status_code == 200, consent_resp.text
    assert consent_resp.json()["consent"]["ai_data_processing_consent"] is True

    # 4. Plan: Create Account & Upload Statement
    acct_resp = mvp_client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={
            "name": "HDFC Primary Checking",
            "account_type": AccountType.SAVINGS.value,
            "institution_name": "HDFC Bank",
            "currency": "INR",
            "initial_balance": 10000.0,
        },
    )
    assert acct_resp.status_code == 201, acct_resp.text
    account_id = acct_resp.json()["id"]

    statement_csv = (
        "Date,Description,Amount,Type\n"
        "2026-11-01,Salary Credit Tech Corp,75000.00,Credit\n"
        "2026-11-03,House Rent Owner,22000.00,Debit\n"
        "2026-11-05,Electricity Bill KSEB,2450.00,Debit\n"
        "2026-11-10,Swiggy Food Delivery,550.00,Debit\n"
    )
    upload_resp = mvp_client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={
            "account_id": account_id,
            "content": statement_csv,
            "format": "csv",
            "filename": "november_statement.csv",
        },
    )
    assert upload_resp.status_code == 200, upload_resp.text
    upload_data = upload_resp.json()
    assert upload_data["imported_count"] == 4

    # 5. Plan: Cash Flow Calculation
    cf_resp = mvp_client.get("/api/v1/plan/cash-flow", headers=headers)
    assert cf_resp.status_code == 200, cf_resp.text
    cf_data = cf_resp.json()
    assert "monthly_breakdown" in cf_data
    assert len(cf_data["monthly_breakdown"]) > 0
    assert cf_data["total_inflow"] == 75000.0
    assert cf_data["net_savings"] == 50000.0

    # 6. Protect: Scam Check
    scam_msg = (
        "URGENT: Your electricity power will be disconnected tonight due to unpaid bill. "
        "Click link to update KYC immediately: http://bit.ly/kseb-pay or call 9876543210."
    )
    scam_resp = mvp_client.post(
        "/api/v1/protect/check",
        headers=headers,
        json={"message": scam_msg},
    )
    assert scam_resp.status_code == 200, scam_resp.text
    scam_data = scam_resp.json()
    analysis = scam_data["analysis"]
    assert analysis["is_scam"] is True
    assert analysis["risk_tier"] in ("HIGH", "CRITICAL", "MEDIUM")
    assert any("1930" in str(rec) for rec in analysis.get("recommendations", []))

    # 7. Protect: Create Recovery Case
    case_resp = mvp_client.post(
        "/api/v1/protect/recovery-cases",
        headers=headers,
        json={
            "scam_type": "electricity_bill_phishing",
            "amount_lost": 2450.0,
            "platform": "SMS",
            "incident_summary": "Received SMS threat about power cut and lost money via UPI link",
        },
    )
    assert case_resp.status_code == 201, case_resp.text
    case_data = case_resp.json()
    assert "id" in case_data or "case_id" in case_data
    assert case_data["checklist"] is not None

    # 8. Borrow: Alternative Credit Assessment (calibrated model or 503 graceful fallback)
    borrow_resp = mvp_client.post("/api/v1/borrow/assess", headers=headers)
    assert borrow_resp.status_code in (201, 503), borrow_resp.text
    if borrow_resp.status_code == 201:
        borrow_data = borrow_resp.json()
        assert "readiness_band" in borrow_data
        assert "legal_disclaimer" in borrow_data
        assert "indicative" in borrow_data["legal_disclaimer"].lower()
    else:
        err = borrow_resp.json()["error"]
        assert err["code"] == "SERVICE_UNAVAILABLE"

    # 9. Assistant: Grounded Knowledge Q&A
    fake_provider = FakeProvider()
    mock_llm = LLMAnswerOutput(
        status="answered",
        answer="Call helpline 1930 immediately within the golden hour to freeze fraudulent transactions [E1].",
        cited_aliases=["E1"],
    )
    fake_provider.enqueue(json.dumps(mock_llm.model_dump()))
    config = LLMConfig(provider="fake", approved_for_real_data=True)
    gateway = LLMGateway(config=config, adapter=fake_provider)
    set_llm_gateway(gateway)

    know_resp = mvp_client.post(
        "/api/v1/assistant/knowledge",
        headers=headers,
        json={"question": "How do I report unauthorized financial fraud in India?"},
    )
    assert know_resp.status_code == 200, know_resp.text
    know_data = know_resp.json()
    assert know_data["status"] in ("answered", "insufficient_evidence")
    if know_data["status"] == "answered":
        assert len(know_data.get("citations", [])) >= 1
        assert "1930" in know_data["answer"]
    assert "disclaimer" in know_data

    # 10. Assistant: Chat Orchestration
    chat_resp = mvp_client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={"question": "What is my total cash flow for this month?"},
    )
    assert chat_resp.status_code == 200, chat_resp.text
    chat_data = chat_resp.json()
    assert chat_data["status"] in (
        "success",
        "clarification_needed",
        "insufficient_evidence",
        "refusal",
        "degraded_fallback",
    )

    # 11. Assistant: Conversation Purge
    purge_resp = mvp_client.request(
        "DELETE",
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"confirm": True, "confirmation_phrase": "DELETE_MY_CONVERSATIONS"},
    )
    assert purge_resp.status_code == 200, purge_resp.text
    assert purge_resp.json()["status"] == "purged"
