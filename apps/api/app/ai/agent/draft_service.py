import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.errors import AppException, ForbiddenException, NotFoundException
from app.models.enums import AuditActor
from app.models.protect import AuditTrail
from app.services.complaint_drafter import draft_fraud_complaint
from app.services.data_sanitizer import mask_sensitive_data

# In-memory registry fallback for zero-DB / unit test scenarios
_IN_MEMORY_DRAFTS: dict[str, dict[str, Any]] = {}


class DraftStatus:
    PENDING = "pending_confirmation"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"


def _format_export_text(draft_meta: dict[str, Any]) -> str:
    """Format confirmed draft as plain text export."""
    subject = draft_meta.get("subject", "Fraud Complaint")
    body = draft_meta.get("body", "")
    bank_name = draft_meta.get("bank_name", "")
    ref = draft_meta.get("reference", "")
    created = draft_meta.get("created_at", "")
    return (
        f"====================================================\n"
        f"FORMAL DISPUTE NOTICE / GRIEVANCE COMPLAINT\n"
        f"Institution: {bank_name}\n"
        f"Reference: {ref}\n"
        f"Generated: {created}\n"
        f"Status: CONFIRMED BY USER (NOT AUTOMATICALLY SUBMITTED)\n"
        f"====================================================\n\n"
        f"Subject: {subject}\n\n"
        f"{body}\n\n"
        f"----------------------------------------------------\n"
        f"Note: This document was drafted by Float at customer request.\n"
        f"Float never files legal complaints or contacts financial institutions autonomously.\n"
        f"Please copy and paste this text into your bank's official grievance portal or email.\n"
    )


async def create_complaint_draft(
    user_id: uuid.UUID,
    bank_name: str,
    account_number_mask: str,
    transaction_reference: str,
    transaction_amount: float,
    incident_date: str | None = None,
    description: str = "",
    victim_name: str = "Account Holder",
    session: AsyncSession | Session | None = None,
) -> dict[str, Any]:
    """Create a structured complaint draft with status pending_confirmation."""
    draft_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=24)

    raw_draft = draft_fraud_complaint(
        victim_name=victim_name,
        bank_name=bank_name,
        account_number_mask=account_number_mask,
        transaction_reference=transaction_reference,
        transaction_amount=transaction_amount,
        incident_date=incident_date,
        description=description,
    )

    masked_desc = mask_sensitive_data(description)
    draft_data: dict[str, Any] = {
        "draft_id": draft_id,
        "user_id": str(user_id),
        "status": DraftStatus.PENDING,
        "bank_name": bank_name,
        "account_number_mask": account_number_mask,
        "reference": transaction_reference,
        "amount": round(transaction_amount, 2),
        "incident_date": incident_date or now.strftime("%Y-%m-%d"),
        "description_masked": masked_desc,
        "subject": raw_draft.get("bank_email_subject", ""),
        "body": raw_draft.get("bank_email_body", ""),
        "helpline_notice": raw_draft.get("cybercrime_helpline_notice", ""),
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    _IN_MEMORY_DRAFTS[draft_id] = draft_data

    if session is not None:
        audit_entry = AuditTrail(
            id=uuid.UUID(draft_id),
            user_id=user_id,
            actor=AuditActor.USER,
            action="DRAFT_CREATED",
            resource_type="complaint_draft",
            resource_id=draft_id,
            metadata_json=draft_data,
        )
        session.add(audit_entry)
        try:
            if isinstance(session, AsyncSession):
                await session.flush()
            else:
                session.flush()
        except Exception:
            pass

    return {
        "draft_id": draft_id,
        "status": DraftStatus.PENDING,
        "bank_name": bank_name,
        "account_number_mask": account_number_mask,
        "reference": transaction_reference,
        "subject": draft_data["subject"],
        "body": draft_data["body"],
        "expires_at": draft_data["expires_at"],
        "notice": "Draft created in pending_confirmation status. It will never be submitted automatically.",
    }


async def get_draft(
    draft_id: str,
    user_id: uuid.UUID,
    session: AsyncSession | Session | None = None,
) -> dict[str, Any]:
    """Retrieve draft ensuring strict cross-user isolation."""
    draft_data: dict[str, Any] | None = _IN_MEMORY_DRAFTS.get(draft_id)

    if session is not None:
        try:
            stmt = select(AuditTrail).where(
                AuditTrail.resource_type == "complaint_draft",
                AuditTrail.resource_id == draft_id,
            )
            if isinstance(session, AsyncSession):
                res = await session.execute(stmt)
                entry = res.scalar_one_or_none()
            else:
                entry = session.execute(stmt).scalar_one_or_none()
            if entry:
                draft_data = entry.metadata_json
        except Exception:
            pass

    if not draft_data:
        raise NotFoundException(f"Draft {draft_id} not found")

    if draft_data.get("user_id") != str(user_id):
        raise ForbiddenException("Access to this draft is forbidden")

    return draft_data


async def confirm_draft(
    draft_id: str,
    user_id: uuid.UUID,
    session: AsyncSession | Session | None = None,
) -> dict[str, Any]:
    """Confirm a draft, enabling plain-text export."""
    draft = await get_draft(draft_id, user_id, session)

    if draft.get("status") == DraftStatus.DISCARDED:
        raise AppException("Cannot confirm a discarded draft", status_code=400, code="INVALID_STATE")

    draft["status"] = DraftStatus.CONFIRMED
    draft["confirmed_at"] = datetime.now(UTC).isoformat()
    _IN_MEMORY_DRAFTS[draft_id] = draft

    if session is not None:
        try:
            audit = AuditTrail(
                id=uuid.uuid4(),
                user_id=user_id,
                actor=AuditActor.USER,
                action="DRAFT_CONFIRMED",
                resource_type="complaint_draft",
                resource_id=draft_id,
                metadata_json=draft,
            )
            session.add(audit)
            if isinstance(session, AsyncSession):
                await session.flush()
            else:
                session.flush()
        except Exception:
            pass

    return {
        "draft_id": draft_id,
        "status": DraftStatus.CONFIRMED,
        "message": "Draft confirmed. You may now export or copy this complaint text.",
    }


async def discard_draft(
    draft_id: str,
    user_id: uuid.UUID,
    session: AsyncSession | Session | None = None,
) -> dict[str, Any]:
    """Discard a draft, preventing export."""
    draft = await get_draft(draft_id, user_id, session)

    draft["status"] = DraftStatus.DISCARDED
    draft["discarded_at"] = datetime.now(UTC).isoformat()
    _IN_MEMORY_DRAFTS[draft_id] = draft

    if session is not None:
        try:
            audit = AuditTrail(
                id=uuid.uuid4(),
                user_id=user_id,
                actor=AuditActor.USER,
                action="DRAFT_DISCARDED",
                resource_type="complaint_draft",
                resource_id=draft_id,
                metadata_json=draft,
            )
            session.add(audit)
            if isinstance(session, AsyncSession):
                await session.flush()
            else:
                session.flush()
        except Exception:
            pass

    return {
        "draft_id": draft_id,
        "status": DraftStatus.DISCARDED,
        "message": "Draft discarded. It cannot be exported or used.",
    }


async def export_draft_text(
    draft_id: str,
    user_id: uuid.UUID,
    session: AsyncSession | Session | None = None,
) -> str:
    """Export draft as copyable plain text. Fails if not confirmed."""
    draft = await get_draft(draft_id, user_id, session)

    if draft.get("status") != DraftStatus.CONFIRMED:
        raise AppException(
            f"Draft {draft_id} cannot be exported because its status is '{draft.get('status')}'. "
            "Only confirmed drafts can be exported.",
            status_code=400,
            code="DRAFT_NOT_CONFIRMED",
        )

    return _format_export_text(draft)
