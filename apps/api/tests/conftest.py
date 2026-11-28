import os
from collections.abc import AsyncGenerator, Generator

os.environ["PFA_APP_ENV"] = "test"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.agent.dependencies import set_orchestrator
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.dependencies import set_llm_gateway
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.dependencies import set_embedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.core.config import Settings
from app.db.session import Base, get_db
from app.main import create_app
from app.models.admin import AdminUser
from app.models.borrow import BorrowAssessment
from app.models.budget import BudgetPlan
from app.models.conversations import Conversation, Message
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.plan import Account, Transaction, TransactionImport
from app.models.protect import (
    AuditTrail,
    RecoveryCase,
    ScamCheckLog,
    ScamSample,
    VerifiedContact,
)
from app.models.recurring import (
    RecurringCommitment,
    RecurringNotification,
    RecurringOccurrence,
)
from app.models.user import (
    AuthAuditLog,
    AuthToken,
    Consent,
    User,
    UserIdentity,
    UserSession,
)

APP_TABLES = [
    User.__table__,
    Consent.__table__,
    UserIdentity.__table__,
    UserSession.__table__,
    AuthToken.__table__,
    AuthAuditLog.__table__,
    Account.__table__,
    TransactionImport.__table__,
    Transaction.__table__,
    ScamCheckLog.__table__,
    RecoveryCase.__table__,
    VerifiedContact.__table__,
    ScamSample.__table__,
    AuditTrail.__table__,
    RecurringCommitment.__table__,
    RecurringOccurrence.__table__,
    RecurringNotification.__table__,
    BorrowAssessment.__table__,
    BudgetPlan.__table__,
    AdminUser.__table__,
    Conversation.__table__,
    Message.__table__,
    KnowledgeDocument.__table__,
    KnowledgeChunk.__table__,
]


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: a developer's local .env must never change test results.
    return Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-for-unit-tests-only-min32chars",
        internal_metrics_token="test-internal-metrics-token",
        _env_file=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)

    # In-memory SQLite async engine with StaticPool so all async sessions share the in-memory DB
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    tables_initialized = False

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        nonlocal tables_initialized
        if not tables_initialized:
            async with engine.begin() as conn:
                await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=APP_TABLES))
            tables_initialized = True

        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def force_test_environment_and_fake_ai(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Force fake provider, fake embedder, and test environment for all tests unless explicitly marked."""
    is_real = (
        request.node.get_closest_marker("real_embedder") is not None
        or request.node.get_closest_marker("live") is not None
    )
    old_env = os.environ.get("PFA_APP_ENV")
    os.environ["PFA_APP_ENV"] = "test"
    from app.core.config import get_settings
    from app.services.auth_lockout import lockout_tracker

    get_settings.cache_clear()
    lockout_tracker.reset()

    if not is_real:
        fake_embedder = FakeEmbedder()
        set_embedder(fake_embedder)

        fake_provider = FakeProvider()
        config = LLMConfig(provider="fake", approved_for_real_data=True)
        fake_gateway = LLMGateway(config=config, adapter=fake_provider)
        set_llm_gateway(fake_gateway)
        set_orchestrator(None)

    yield

    if not is_real:
        set_embedder(None)
        set_llm_gateway(None)
        set_orchestrator(None)

    if old_env is not None:
        os.environ["PFA_APP_ENV"] = old_env
    else:
        os.environ.pop("PFA_APP_ENV", None)
    get_settings.cache_clear()

