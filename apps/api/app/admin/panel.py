from pathlib import Path
from typing import Any

from sqladmin import Admin
from sqladmin.authentication import login_required
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import Response

from app.admin.auth import AdminAuth
from app.admin.views import ADMIN_ALLOWED_VIEWS, PROHIBITED_MODELS
from app.core.config import Settings
from app.db.session import get_async_session_factory
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.protect import VerifiedContact


class FloatAdmin(Admin):
    """Customized SQLAdmin class with operational dashboard metrics."""

    @login_required
    async def index(self, request: Request) -> Response:
        session_factory = get_async_session_factory()
        doc_status_counts: dict[str, int] = {}
        published_chunk_count: int = 0
        last_ingestion_time: str | None = None
        verified_contacts_count: int = 0

        async with session_factory() as session:
            # 1. Documents by lifecycle status
            stmt_status = select(
                KnowledgeDocument.status,
                func.count(KnowledgeDocument.id),
            ).group_by(KnowledgeDocument.status)
            res_status = await session.execute(stmt_status)
            for status, count in res_status.all():
                doc_status_counts[status] = count

            # 2. Published chunks count
            stmt_chunks = (
                select(func.count(KnowledgeChunk.id))
                .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(KnowledgeDocument.status == "published")
            )
            res_chunks = await session.execute(stmt_chunks)
            published_chunk_count = res_chunks.scalar() or 0

            # 3. Last ingestion time
            stmt_last_ingest = select(func.max(KnowledgeDocument.created_at))
            res_last_ingest = await session.execute(stmt_last_ingest)
            last_dt = res_last_ingest.scalar()
            if last_dt:
                last_ingestion_time = last_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

            # 4. Verified contacts count
            stmt_contacts = select(func.count(VerifiedContact.id))
            res_contacts = await session.execute(stmt_contacts)
            verified_contacts_count = res_contacts.scalar() or 0

        context = {
            "request": request,
            "title": self.title,
            "doc_status_counts": doc_status_counts,
            "published_chunk_count": published_chunk_count,
            "last_ingestion_time": last_ingestion_time,
            "verified_contacts_count": verified_contacts_count,
        }
        return await self.templates.TemplateResponse(request, "sqladmin/index.html", context)


def setup_admin_panel(app: Any, settings: Settings, engine: Any = None) -> FloatAdmin | None:
    """Mount SQLAdmin internal panel to FastAPI application if enabled."""
    if not settings.admin_enabled:
        return None

    secret_key = (
        settings.admin_session_secret_key.get_secret_value()
        if settings.admin_session_secret_key
        else settings.jwt_secret_key
    )

    auth_backend = AdminAuth(
        secret_key=secret_key,
        session_expire_seconds=settings.admin_session_expire_seconds,
    )

    if engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    templates_dir = str(Path(__file__).parent.parent / "templates")

    admin = FloatAdmin(
        app=app,
        engine=engine,
        base_url="/admin",
        title="Float Admin",
        logo_url="/static/admin/logo.svg",
        templates_dir=templates_dir,
        authentication_backend=auth_backend,
    )

    # Register only permitted operational models with strict safety check
    for view_cls in ADMIN_ALLOWED_VIEWS:
        model_name = getattr(view_cls.model, "__name__", "")
        if model_name in PROHIBITED_MODELS:
            raise RuntimeError(
                f"Security violation: model '{model_name}' is sensitive consumer financial data and "
                "is strictly prohibited from registration in the admin panel."
            )
        admin.add_model_view(view_cls)

    return admin
