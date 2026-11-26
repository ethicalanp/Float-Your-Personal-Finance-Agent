import re
import uuid
from typing import Any

from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.admin.audit import record_admin_audit
from app.ai.rag.dependencies import get_embedder
from app.ai.rag.repository import DocumentApprovalRefusedError, KnowledgeRepository
from app.db.session import get_async_session_factory
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.protect import AuditTrail, VerifiedContact
from app.models.user import Consent, User


def mask_user_email(email: str | None) -> str:
    """Mask email address as a***@domain for privacy by default."""
    if not email or "@" not in email:
        return "***"
    parts = email.split("@", 1)
    name, domain = parts[0], parts[1]
    masked_name = (name[0] + "***") if len(name) > 0 else "***"
    return f"{masked_name}@{domain}"


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-users"

    # Strictly read-only per requirements: no create, edit, delete, export
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False

    page_size = 20
    page_size_options = [10, 20, 50, 100]

    column_default_sort = [(User.created_at, True)]

    # Explicit column allowlist: short id, email, created_at, last_login_at, status, ai_data_processing consent
    column_list = [
        User.id,
        User.email,
        User.created_at,
        "last_login_at",
        User.is_active,
        "ai_data_processing_consent",
    ]

    column_details_list = [
        User.id,
        User.email,
        User.created_at,
        "last_login_at",
        User.is_active,
        "ai_data_processing_consent",
    ]

    column_labels = {
        User.id: "Short ID",
        User.email: "Email",
        User.created_at: "Created At",
        "last_login_at": "Last Login At",
        User.is_active: "Status",
        "ai_data_processing_consent": "AI Data Processing Consent",
    }

    column_formatters = {
        User.id: lambda m, a: str(m.id)[:8],
        User.email: lambda m, a: mask_user_email(m.email),
        User.is_active: lambda m, a: "active" if m.is_active else "disabled",
        "last_login_at": lambda m, a: "Not tracked yet",
    }

    column_formatters_detail = {
        User.id: lambda m, a: str(m.id)[:8],
        User.email: lambda m, a: mask_user_email(m.email),
        User.is_active: lambda m, a: "active" if m.is_active else "disabled",
        "last_login_at": lambda m, a: "Not tracked yet",
    }

    column_filters = [
        User.is_active,
        User.created_at,
        Consent.consent_type,
    ]

    def search_query(self, stmt: Any, term: str) -> Any:
        """Search by exact email or exact id only."""
        from sqlalchemy import false, or_

        term = term.strip()
        expressions = []
        expressions.append(User.normalized_email == term.lower())
        try:
            val_uuid = uuid.UUID(term)
            expressions.append(User.id == val_uuid)
        except ValueError:
            pass
        return stmt.filter(or_(false(), *expressions))

    @action(
        name="reveal_email",
        label="Reveal Email",
        confirmation_message="Reveal unmasked email address for this user? This access will be permanently audited.",
        add_in_detail=True,
        add_in_list=False,
    )
    async def reveal_email(self, request: Request) -> Response:
        pks = request.query_params.get("pks", "").split(",")
        admin_id = request.session.get("admin_id")
        admin_username = request.session.get("admin_username", "admin")
        session_factory = get_async_session_factory()

        if not pks or not pks[0].strip():
            return RedirectResponse(request.url_for("admin:list", identity=self.identity), status_code=303)

        try:
            user_id = uuid.UUID(pks[0].strip())
        except ValueError:
            return RedirectResponse(request.url_for("admin:list", identity=self.identity), status_code=303)

        async with session_factory() as session:
            user = await session.get(User, user_id)
            if not user:
                return RedirectResponse(request.url_for("admin:list", identity=self.identity), status_code=303)

            await record_admin_audit(
                session=session,
                admin_id=admin_id,
                admin_username=admin_username,
                action="admin_reveal_email",
                resource_type="users",
                resource_id=str(user.id),
                user_id=user.id,
                metadata={},  # never the email
            )
            await session.commit()
            revealed_email = user.email

        context = {
            "request": request,
            "title": "Revealed User Email",
            "user_id": str(user_id),
            "email": revealed_email,
            "back_url": str(request.url_for("admin:details", identity=self.identity, pk=str(user_id))),
        }
        return await self.templates.TemplateResponse(request, "sqladmin/reveal_email.html", context)


class KnowledgeDocumentAdmin(ModelView, model=KnowledgeDocument):
    name = "Knowledge Document"
    name_plural = "Knowledge Documents"
    icon = "fa-solid fa-book"

    # Strict lifecycle guardrails: No direct creation, manual editing of status, or deletion
    can_create = False
    can_edit = False
    can_delete = False

    column_list = [
        KnowledgeDocument.title,
        KnowledgeDocument.publisher,
        KnowledgeDocument.language,
        KnowledgeDocument.version,
        KnowledgeDocument.status,
        KnowledgeDocument.effective_date,
    ]

    column_searchable_list = [
        KnowledgeDocument.title,
        KnowledgeDocument.publisher,
    ]

    column_filters = [
        KnowledgeDocument.status,
        KnowledgeDocument.language,
        KnowledgeDocument.publisher,
    ]

    column_details_list = [
        KnowledgeDocument.id,
        KnowledgeDocument.title,
        KnowledgeDocument.publisher,
        KnowledgeDocument.source_url,
        KnowledgeDocument.licence_note,
        KnowledgeDocument.version,
        KnowledgeDocument.status,
        KnowledgeDocument.language,
        KnowledgeDocument.doc_type,
        KnowledgeDocument.publication_date,
        KnowledgeDocument.effective_date,
        KnowledgeDocument.content_hash,
        KnowledgeDocument.reviewed_by,
        KnowledgeDocument.reviewed_at,
        KnowledgeDocument.supersedes_id,
        KnowledgeDocument.created_at,
    ]

    column_formatters = {
        KnowledgeDocument.title: lambda m, a: (m.title[:60] + "...") if len(m.title) > 60 else m.title,
    }

    column_formatters_detail = {
        KnowledgeDocument.licence_note: lambda m, a: (
            (m.licence_note[:300] + "...")
            if m.licence_note and len(m.licence_note) > 300
            else (m.licence_note or "")
        ),
        KnowledgeDocument.source_url: lambda m, a: (
            (m.source_url[:120] + "...") if len(m.source_url) > 120 else m.source_url
        ),
    }

    @action(
        name="submit_for_review",
        label="Submit for Review",
        confirmation_message="Submit selected draft document(s) for editorial review?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def submit_for_review(self, request: Request) -> Response:
        pks = request.query_params.get("pks", "").split(",")
        admin_id = request.session.get("admin_id")
        admin_username = request.session.get("admin_username", "admin")
        session_factory = get_async_session_factory()

        async with session_factory() as session:
            for pk in pks:
                if not pk.strip():
                    continue
                doc_id = uuid.UUID(pk.strip())
                doc = await session.get(KnowledgeDocument, doc_id)
                if not doc:
                    continue
                if doc.status != "draft":
                    continue
                doc.status = "review"
                await record_admin_audit(
                    session=session,
                    admin_id=admin_id,
                    admin_username=admin_username,
                    action="admin_submit_review",
                    resource_type="knowledge_documents",
                    resource_id=str(doc.id),
                    metadata={"title": doc.title, "new_status": "review"},
                )
            await session.commit()

        referer = request.headers.get("referer")
        return RedirectResponse(referer or request.url_for("admin:list", identity=self.identity), status_code=303)

    @action(
        name="publish_document",
        label="Publish",
        confirmation_message="Publish selected document(s) and run verification smoke tests?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def publish_document(self, request: Request) -> Response:
        pks = request.query_params.get("pks", "").split(",")
        admin_id = request.session.get("admin_id")
        admin_username = request.session.get("admin_username", "admin")
        session_factory = get_async_session_factory()
        embedder = get_embedder()

        async with session_factory() as session:
            repo = KnowledgeRepository(session)
            for pk in pks:
                if not pk.strip():
                    continue
                doc_id = uuid.UUID(pk.strip())
                try:
                    await repo.approve_document(doc_id=doc_id, reviewer=admin_username, embedder=embedder)
                    await record_admin_audit(
                        session=session,
                        admin_id=admin_id,
                        admin_username=admin_username,
                        action="admin_publish",
                        resource_type="knowledge_documents",
                        resource_id=str(doc_id),
                        metadata={"reviewer": admin_username, "new_status": "published"},
                    )
                except DocumentApprovalRefusedError as e:
                    # Refusal due to state or licensing invariants
                    await record_admin_audit(
                        session=session,
                        admin_id=admin_id,
                        admin_username=admin_username,
                        action="admin_publish_refused",
                        resource_type="knowledge_documents",
                        resource_id=str(doc_id),
                        metadata={"reason": str(e)},
                    )
            await session.commit()

        referer = request.headers.get("referer")
        return RedirectResponse(referer or request.url_for("admin:list", identity=self.identity), status_code=303)

    @action(
        name="archive_document",
        label="Archive",
        confirmation_message="Archive selected document(s)?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def archive_document(self, request: Request) -> Response:
        pks = request.query_params.get("pks", "").split(",")
        admin_id = request.session.get("admin_id")
        admin_username = request.session.get("admin_username", "admin")
        session_factory = get_async_session_factory()

        async with session_factory() as session:
            repo = KnowledgeRepository(session)
            for pk in pks:
                if not pk.strip():
                    continue
                doc_id = uuid.UUID(pk.strip())
                await repo.archive_document(doc_id)
                await record_admin_audit(
                    session=session,
                    admin_id=admin_id,
                    admin_username=admin_username,
                    action="admin_archive",
                    resource_type="knowledge_documents",
                    resource_id=str(doc_id),
                    metadata={"new_status": "archived"},
                )
            await session.commit()

        referer = request.headers.get("referer")
        return RedirectResponse(referer or request.url_for("admin:list", identity=self.identity), status_code=303)

    @action(
        name="supersede_document",
        label="Mark Superseded",
        confirmation_message="Mark selected document(s) as superseded?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def supersede_document(self, request: Request) -> Response:
        pks = request.query_params.get("pks", "").split(",")
        admin_id = request.session.get("admin_id")
        admin_username = request.session.get("admin_username", "admin")
        session_factory = get_async_session_factory()

        async with session_factory() as session:
            for pk in pks:
                if not pk.strip():
                    continue
                doc_id = uuid.UUID(pk.strip())
                doc = await session.get(KnowledgeDocument, doc_id)
                if doc and doc.status == "published":
                    doc.status = "superseded"
                    await record_admin_audit(
                        session=session,
                        admin_id=admin_id,
                        admin_username=admin_username,
                        action="admin_supersede",
                        resource_type="knowledge_documents",
                        resource_id=str(doc_id),
                        metadata={"new_status": "superseded"},
                    )
            await session.commit()

        referer = request.headers.get("referer")
        return RedirectResponse(referer or request.url_for("admin:list", identity=self.identity), status_code=303)


class KnowledgeChunkAdmin(ModelView, model=KnowledgeChunk):
    name = "Knowledge Chunk"
    name_plural = "Knowledge Chunks"
    icon = "fa-solid fa-cubes"

    can_create = False
    can_edit = False
    can_delete = False

    # Explicit column list: NEVER show embedding or content_tsv
    column_list = [
        KnowledgeChunk.document_id,
        KnowledgeChunk.chunk_index,
        KnowledgeChunk.language,
        KnowledgeChunk.token_count,
    ]

    column_details_list = [
        KnowledgeChunk.id,
        KnowledgeChunk.document_id,
        KnowledgeChunk.chunk_index,
        KnowledgeChunk.language,
        KnowledgeChunk.token_count,
        KnowledgeChunk.content,
    ]

    column_formatters_detail = {
        KnowledgeChunk.content: lambda m, a: (m.content[:300] + "...") if len(m.content) > 300 else m.content,
    }


class VerifiedContactAdmin(ModelView, model=VerifiedContact):
    name = "Verified Contact"
    name_plural = "Verified Contacts"
    icon = "fa-solid fa-phone-shield"

    can_create = True
    can_edit = True
    can_delete = True

    column_list = [
        VerifiedContact.institution,
        VerifiedContact.contact_type,
        VerifiedContact.country_code,
        VerifiedContact.toll_free_number,
        VerifiedContact.fraud_reporting_email,
        VerifiedContact.website,
        VerifiedContact.last_verified_at,
        VerifiedContact.valid_from,
        VerifiedContact.valid_until,
    ]

    column_searchable_list = [
        VerifiedContact.institution,
        VerifiedContact.toll_free_number,
        VerifiedContact.fraud_reporting_email,
    ]

    column_filters = [
        VerifiedContact.contact_type,
        VerifiedContact.country_code,
    ]

    async def on_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> None:
        """Validate phone, email, and URL format before saving."""
        phone = data.get("toll_free_number")
        if phone:
            phone_clean = re.sub(r"[\s\-\(\)]", "", str(phone))
            if not re.match(r"^\+?[0-9]{3,16}$", phone_clean):
                raise ValueError(f"Invalid phone format: '{phone}'. Expected 3-16 digits with optional '+'.")

        for url_field in ("source_url", "website"):
            url = data.get(url_field)
            if url:
                if not re.match(r"^https?://[^\s]+$", str(url)):
                    raise ValueError(f"Invalid URL format for {url_field}: '{url}'. Must start with http:// or https://")

        email = data.get("fraud_reporting_email")
        if email:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(email)):
                raise ValueError(f"Invalid email format: '{email}'.")

    async def after_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> Response | None:
        admin_id = request.session.get("admin_id")
        admin_username = request.session.get("admin_username", "admin")
        action_name = "admin_create_verified_contact" if is_created else "admin_edit_verified_contact"
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            await record_admin_audit(
                session=session,
                admin_id=admin_id,
                admin_username=admin_username,
                action=action_name,
                resource_type="verified_contacts",
                resource_id=str(getattr(model, "id", "")),
                metadata={"institution": getattr(model, "institution", "")},
            )
            await session.commit()
        return None

    async def after_model_delete(self, model: Any, request: Request) -> None:
        admin_id = request.session.get("admin_id")
        admin_username = request.session.get("admin_username", "admin")
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            await record_admin_audit(
                session=session,
                admin_id=admin_id,
                admin_username=admin_username,
                action="admin_delete_verified_contact",
                resource_type="verified_contacts",
                resource_id=str(getattr(model, "id", "")),
                metadata={"institution": getattr(model, "institution", "")},
            )
            await session.commit()
        return None


class AuditTrailAdmin(ModelView, model=AuditTrail):
    name = "Audit Record"
    name_plural = "Audit Records"
    icon = "fa-solid fa-shield-halved"

    can_create = False
    can_edit = False
    can_delete = False
    can_export = False

    column_list = [
        AuditTrail.id,
        AuditTrail.actor,
        AuditTrail.action,
        AuditTrail.resource_type,
        AuditTrail.resource_id,
        AuditTrail.created_at,
    ]

    column_filters = [
        AuditTrail.action,
        AuditTrail.resource_type,
        AuditTrail.created_at,
    ]

    column_searchable_list = [
        AuditTrail.action,
        AuditTrail.resource_type,
        AuditTrail.resource_id,
    ]

    column_details_list = [
        AuditTrail.id,
        AuditTrail.user_id,
        AuditTrail.actor,
        AuditTrail.action,
        AuditTrail.resource_type,
        AuditTrail.resource_id,
        AuditTrail.created_at,
        AuditTrail.metadata_json,
    ]

    column_default_sort = ("created_at", True)

    column_formatters = {
        AuditTrail.actor: lambda m, a: (
            f"admin:{m.metadata_json['admin_id'][:8]}"
            if m.metadata_json and m.metadata_json.get("admin_id") and m.metadata_json.get("admin_id") != "unknown"
            else m.actor.value
        ),
    }


ADMIN_ALLOWED_VIEWS = [
    UserAdmin,
    KnowledgeDocumentAdmin,
    KnowledgeChunkAdmin,
    VerifiedContactAdmin,
    AuditTrailAdmin,
]

# Sensitive model classes prohibited from ever appearing in the admin panel
PROHIBITED_MODELS = {
    "Consent",
    "Account",
    "Transaction",
    "TransactionImport",
    "Conversation",
    "Message",
    "BorrowAssessment",
    "RecurringCommitment",
    "RecurringOccurrence",
    "RecurringNotification",
}

# Strict column allowlist for User view
USER_ALLOWED_COLUMNS = {
    "id",
    "email",
    "created_at",
    "last_login_at",
    "is_active",
    "status",
    "ai_data_processing",
    "ai_data_processing_consent",
}

USER_SENSITIVE_FORBIDDEN_COLUMNS = {
    "hashed_password",
    "password",
    "normalized_email",
    "full_name",
    "token",
    "tokens",
    "phone",
    "dob",
    "pan",
    "aadhaar",
}
