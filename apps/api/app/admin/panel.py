from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqladmin import Admin
from sqladmin.authentication import login_required
from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import Response

from app.admin.auth import AdminAuth
from app.admin.views import (
    ADMIN_ALLOWED_VIEWS,
    PROHIBITED_MODELS,
    USER_ALLOWED_COLUMNS,
    USER_SENSITIVE_FORBIDDEN_COLUMNS,
)
from app.core.config import Settings
from app.db.session import get_async_session_factory
from app.models.enums import ConsentType
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.protect import VerifiedContact
from app.models.user import Consent, User


class FloatAdmin(Admin):
    """Customized SQLAdmin class with operational dashboard metrics."""

    @login_required
    async def index(self, request: Request) -> Response:
        session_factory = get_async_session_factory()
        doc_status_counts: dict[str, int] = {}
        published_chunk_count: int = 0
        last_ingestion_time: str | None = None
        verified_contacts_count: int = 0
        now = datetime.now(UTC)
        cutoff_7d = now - timedelta(days=7)
        cutoff_30d = now - timedelta(days=30)

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

            # 5. User counts (strictly counts only, zero financial or conversation data)
            total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
            users_7d = (
                await session.execute(select(func.count(User.id)).where(User.created_at >= cutoff_7d))
            ).scalar() or 0
            users_30d = (
                await session.execute(select(func.count(User.id)).where(User.created_at >= cutoff_30d))
            ).scalar() or 0
            active_users = (
                await session.execute(select(func.count(User.id)).where(User.is_active.is_(True)))
            ).scalar() or 0
            disabled_users = (
                await session.execute(select(func.count(User.id)).where(User.is_active.is_(False)))
            ).scalar() or 0
            ai_consented_users = (
                await session.execute(
                    select(func.count(func.distinct(Consent.user_id))).where(
                        Consent.consent_type == ConsentType.AI_DATA_PROCESSING,
                        Consent.revoked_at.is_(None),
                    )
                )
            ).scalar() or 0

        user_metrics = {
            "total_users": total_users,
            "new_7d": users_7d,
            "new_30d": users_30d,
            "active": active_users,
            "disabled": disabled_users,
            "ai_consented": ai_consented_users,
        }

        context = {
            "request": request,
            "title": self.title,
            "doc_status_counts": doc_status_counts,
            "published_chunk_count": published_chunk_count,
            "last_ingestion_time": last_ingestion_time,
            "verified_contacts_count": verified_contacts_count,
            "user_metrics": user_metrics,
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

        # Enforce strict allowlist and read-only invariants for User view
        if model_name == "User":
            if getattr(view_cls, "can_create", True) or getattr(view_cls, "can_edit", True) or \
               getattr(view_cls, "can_delete", True) or getattr(view_cls, "can_export", True):
                raise RuntimeError("Security violation: UserAdmin must be strictly read-only with export disabled.")

            for attr in ("column_list", "column_details_list"):
                raw_cols = getattr(view_cls, attr, [])
                for col in raw_cols:
                    col_name = getattr(col, "name", str(col))
                    if col_name in USER_SENSITIVE_FORBIDDEN_COLUMNS:
                        raise RuntimeError(
                            f"Security violation: Sensitive User column '{col_name}' rendered in {attr}."
                        )
                    if col_name not in USER_ALLOWED_COLUMNS:
                        raise RuntimeError(
                            f"Security violation: User column '{col_name}' in {attr} is not allowlisted."
                        )

        admin.add_model_view(view_cls)

    return admin
