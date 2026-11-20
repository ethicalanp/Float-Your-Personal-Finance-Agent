import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.session import Base, get_db
from app.main import create_app
from app.models.borrow import BorrowAssessment
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
from app.models.user import Consent, User

APP_TABLES = [
    User.__table__,
    Consent.__table__,
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
]


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: a developer's local .env must never change test results.
    return Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-for-unit-tests-only-min32chars",
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

    async def init_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=APP_TABLES))

    asyncio.run(init_db())

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
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
