import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqladmin import ModelView
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.admin.auth import AdminAuth
from app.admin.create_admin import create_or_update_admin
from app.admin.panel import setup_admin_panel
from app.admin.views import (
    ADMIN_ALLOWED_VIEWS,
    PROHIBITED_MODELS,
    KnowledgeChunkAdmin,
    KnowledgeDocumentAdmin,
    VerifiedContactAdmin,
)
from app.core.config import Settings
from app.db.session import Base
from app.main import create_app
from app.models.knowledge import KnowledgeDocument
from app.models.protect import AuditTrail, VerifiedContact
from app.models.user import User
from tests.conftest import APP_TABLES


class MockAsyncSessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def __call__(self) -> "MockAsyncSessionFactory":
        return self

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = list(APP_TABLES) + [KnowledgeDocument.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def admin_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-for-admin-tests-min32chars",
        admin_enabled=True,
        admin_allowed_ips="127.0.0.1,::1,testclient",
        admin_session_secret_key="test-admin-session-secret-min32chars",
        admin_session_expire_seconds=1800,
        _env_file=None,
    )


# 1. Admin Disabled by Default
def test_admin_disabled_by_default(settings: Settings) -> None:
    assert settings.admin_enabled is False
    app = create_app(settings)
    client = TestClient(app)
    resp = client.get("/admin")
    assert resp.status_code == 404


# 2. IP Allowlist Middleware
def test_admin_ip_allowlist_blocks_unauthorized_ip(admin_settings: Settings) -> None:
    admin_settings.admin_allowed_ips = "127.0.0.1,::1"
    app = create_app(admin_settings)

    # Unauthorized IP via client or forwarded header
    client = TestClient(app, client=("198.51.100.5", 12345))
    resp = client.get("/admin", headers={"x-forwarded-for": "198.51.100.5"})
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "ADMIN_FORBIDDEN_IP"


def test_admin_ip_allowlist_permits_authorized_ip(admin_settings: Settings) -> None:
    admin_settings.admin_allowed_ips = "127.0.0.1,::1,testclient"
    app = create_app(admin_settings)

    client = TestClient(app, client=("127.0.0.1", 12345))
    resp = client.get("/admin", follow_redirects=False)
    # Should redirect to login (302/303) or return login page (not 403 forbidden)
    assert resp.status_code in (200, 302, 303, 307)


# 3. Authentication, Sessions & Rate Limiting
@pytest.mark.asyncio
async def test_admin_auth_login_and_rate_limit(db_session: AsyncSession) -> None:
    auth = AdminAuth(
        secret_key="test-secret-min-32-chars-long-here",
        session_expire_seconds=60,
        session_factory=MockAsyncSessionFactory(db_session),
    )
    auth._clear_attempts("127.0.0.1")

    # Create admin user
    await create_or_update_admin(
        username="secops_admin",
        password="ValidPassword123!",
        session=db_session,
    )

    # Simulated request helper
    def make_mock_request(form_data: dict[str, str], ip: str = "127.0.0.1") -> Request:
        req = MagicMock(spec=Request)
        req.client = MagicMock()
        req.client.host = ip
        req.session = {}

        async def form():
            return form_data

        req.form = form
        return req

    # 1. Invalid password
    bad_req = make_mock_request({"username": "secops_admin", "password": "WrongPassword!"})
    success = await auth.login(bad_req)
    assert success is False

    # 2. Rate limit triggering: 5 failed attempts
    for _ in range(4):
        await auth.login(bad_req)

    # 6th attempt is rate-limited even with the right password
    good_req = make_mock_request({"username": "secops_admin", "password": "ValidPassword123!"})
    assert await auth.login(good_req) is False

    # Clear rate limit and login successfully
    auth._clear_attempts("127.0.0.1")
    assert await auth.login(good_req) is True
    assert "admin_id" in good_req.session
    assert good_req.session["admin_username"] == "secops_admin"

    # Authenticate check succeeds
    assert await auth.authenticate(good_req) is True

    # Logout check
    await auth.logout(good_req)
    assert "admin_id" not in good_req.session
    assert await auth.authenticate(good_req) is False


# 4. Sensitive Models Absent Guardrail
def test_sensitive_models_absent_from_admin_registry() -> None:
    for view_cls in ADMIN_ALLOWED_VIEWS:
        model_cls = getattr(view_cls, "model", None)
        assert model_cls is not None
        model_name = getattr(model_cls, "__name__", "")
        assert model_name not in PROHIBITED_MODELS, f"Prohibited sensitive model {model_name} found in admin views!"

    # Test that registering a prohibited model raises a security error
    class IllegalUserView(ModelView, model=User):
        pass

    mock_app = MagicMock()
    mock_settings = Settings(
        app_env="test",
        admin_enabled=True,
        jwt_secret_key="test-key-must-be-at-least-32-characters-long",
        _env_file=None,
    )

    from unittest.mock import patch
    with patch("app.admin.panel.ADMIN_ALLOWED_VIEWS", [IllegalUserView]):
        with pytest.raises(RuntimeError, match="Security violation: model 'User' is sensitive consumer financial data"):
            setup_admin_panel(mock_app, mock_settings)


# 5. Embedding and content_tsv Never Rendered
def test_embedding_and_content_tsv_never_rendered() -> None:
    chunk_columns = [getattr(col, "name", str(col)) for col in KnowledgeChunkAdmin.column_list]
    chunk_detail_columns = [getattr(col, "name", str(col)) for col in KnowledgeChunkAdmin.column_details_list]

    assert "embedding" not in chunk_columns
    assert "content_tsv" not in chunk_columns
    assert "embedding" not in chunk_detail_columns
    assert "content_tsv" not in chunk_detail_columns


# 6. Verified Contact Format Validation & Audit Hooks
@pytest.mark.asyncio
async def test_verified_contact_validation(db_session: AsyncSession) -> None:
    admin_view = VerifiedContactAdmin()
    mock_req = MagicMock(spec=Request)
    mock_req.session = {"admin_username": "compliance_admin"}

    # Invalid phone format
    with pytest.raises(ValueError, match="Invalid phone format"):
        await admin_view.on_model_change(
            data={"toll_free_number": "not-a-number"},
            model=None,
            is_created=True,
            request=mock_req,
        )

    # Invalid URL format
    with pytest.raises(ValueError, match="Invalid URL format"):
        await admin_view.on_model_change(
            data={"source_url": "ftp://malicious.link"},
            model=None,
            is_created=True,
            request=mock_req,
        )

    # Invalid email format
    with pytest.raises(ValueError, match="Invalid email format"):
        await admin_view.on_model_change(
            data={"fraud_reporting_email": "invalid_email"},
            model=None,
            is_created=True,
            request=mock_req,
        )

    # Valid contact triggers audit entry in after_model_change
    contact = VerifiedContact(
        id=uuid.uuid4(),
        institution="Reserve Bank of India",
        contact_type="regulator",
        toll_free_number="14440",
        fraud_reporting_email="report@rbi.org.in",
        source_url="https://rbi.org.in",
        last_verified_at=date.today(),
        valid_from=date.today(),
    )
    db_session.add(contact)
    await db_session.commit()

    from unittest.mock import patch
    with patch("app.admin.views.get_async_session_factory", return_value=MockAsyncSessionFactory(db_session)):
        await admin_view.after_model_change(data={}, model=contact, is_created=True, request=mock_req)

    stmt_audit = select(AuditTrail).where(AuditTrail.resource_id == str(contact.id))
    audit_entry = (await db_session.execute(stmt_audit)).scalars().first()
    assert audit_entry is not None
    assert audit_entry.action == "admin_create_verified_contact"
    assert audit_entry.metadata_json["admin_username"] == "compliance_admin"


# 7. Knowledge Document Lifecycle Actions & State Transitions
@pytest.mark.asyncio
async def test_knowledge_document_lifecycle_actions(db_session: AsyncSession) -> None:
    doc = KnowledgeDocument(
        id=uuid.uuid4(),
        title="RBI Master Direction - Digital Payment Security Controls",
        publisher="RBI",
        source_url="https://rbi.org.in/payment_security.pdf",
        licence_note="Open Government Data Licence India",
        version="1.0",
        status="draft",
        language="en",
        effective_date=datetime.now(UTC),
    )
    db_session.add(doc)
    await db_session.commit()

    view = KnowledgeDocumentAdmin()

    # 1. Submit for review action
    req_review = MagicMock(spec=Request)
    session_data = {
        "admin_id": str(uuid.uuid4()),
        "admin_username": "editorial_admin",
        "login_time": datetime.now(UTC).timestamp(),
    }
    req_review.session = session_data
    req_review.scope = {"session": session_data, "type": "http"}
    req_review.state = MagicMock()
    req_review.query_params = {"pks": str(doc.id)}
    req_review.headers = {"referer": "/admin/knowledge-document/list"}

    from unittest.mock import patch
    with patch("app.admin.views.get_async_session_factory", return_value=MockAsyncSessionFactory(db_session)):
        resp = await view.submit_for_review(req_review)
        assert isinstance(resp, RedirectResponse)

    stmt_doc = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.id == doc.id)
        .execution_options(populate_existing=True)
    )
    reloaded = (await db_session.execute(stmt_doc)).scalars().one()
    assert reloaded.status == "review"

    # Verify audit entry for submit review
    stmt = select(AuditTrail).where(AuditTrail.action == "admin_submit_review", AuditTrail.resource_id == str(doc.id))
    audit_review = (await db_session.execute(stmt)).scalars().first()
    assert audit_review is not None
    assert audit_review.metadata_json["new_status"] == "review"

    # 2. Archive action
    with patch("app.admin.views.get_async_session_factory", return_value=MockAsyncSessionFactory(db_session)):
        resp_archive = await view.archive_document(req_review)
        assert isinstance(resp_archive, RedirectResponse)

    reloaded_arch = (await db_session.execute(stmt_doc)).scalars().one()
    assert reloaded_arch.status == "archived"

    stmt_arch = select(AuditTrail).where(AuditTrail.action == "admin_archive", AuditTrail.resource_id == str(doc.id))
    audit_arch = (await db_session.execute(stmt_arch)).scalars().first()
    assert audit_arch is not None
    assert audit_arch.metadata_json["new_status"] == "archived"
