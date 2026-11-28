import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.dependencies import get_current_active_user, get_db, require_recent_auth
from app.core.errors import ConflictException, ValidationException
from app.models.borrow import BorrowAssessment
from app.models.conversations import Conversation, Message
from app.models.enums import AuthAuditEventType, AuthProvider, ConsentType
from app.models.plan import Account, Transaction
from app.models.protect import AuditTrail, ScamCheckLog
from app.models.recurring import RecurringCommitment
from app.models.subscriptions_networth import (
    NetWorthItem,
    NetWorthSnapshot,
    SubscriptionLeakDecision,
)
from app.models.user import AuthAuditLog, Consent, User, UserIdentity, UserSession
from app.services.auth_audit import log_auth_event

router = APIRouter(prefix="/me", tags=["Profile & Data Rights"])

# Allow Latin, Malayalam (\u0D00-\u0D7F), digits, spaces, and common name punctuation.
DISPLAY_NAME_PATTERN = re.compile(r"^[\w\s.\-'\u0D00-\u0D7F]+$", re.UNICODE)
LOCALE_PATTERN = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
ALLOWED_NOTIFICATION_KEYS = {"security_alerts", "recurring_reminders", "product_updates"}
DEFAULT_NOTIFICATION_PREFS = {
    "security_alerts": True,
    "recurring_reminders": True,
    "product_updates": False,
}


class ProfileResponse(BaseModel):
    user_id: str
    full_name: str
    email: str | None = None
    phone_number: str | None = None
    preferred_language: str
    locale: str
    notification_preferences: dict[str, bool]
    methods: list[str]
    consent: dict[str, Any]
    deletion_requested_at: str | None = None
    deletion_scheduled_for: str | None = None
    created_at: str


class ProfileUpdateRequest(BaseModel):
    # Reject unknown fields (including email/phone_number attempts) so they cannot be changed directly.
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    preferred_language: Literal["en", "ml", "manglish"] | None = None
    locale: str | None = Field(default=None, min_length=2, max_length=16)
    notification_preferences: dict[str, bool] | None = None


class DeleteAccountResponse(BaseModel):
    status: str
    deletion_requested_at: str
    deletion_scheduled_for: str
    grace_period_days: int
    message: str


def _merged_notif_prefs(raw: dict[str, Any] | None) -> dict[str, bool]:
    merged = dict(DEFAULT_NOTIFICATION_PREFS)
    if isinstance(raw, dict):
        for k in ALLOWED_NOTIFICATION_KEYS:
            if k in raw:
                merged[k] = bool(raw[k])
    return merged


async def _build_profile_response(user: User, db: AsyncSession) -> ProfileResponse:
    ident_res = await db.execute(select(UserIdentity).where(UserIdentity.user_id == user.id))
    identities = ident_res.scalars().all()
    methods: list[str] = []
    if user.hashed_password or any(i.provider == AuthProvider.PASSWORD for i in identities):
        methods.append("password")
    if any(i.provider == AuthProvider.GOOGLE for i in identities):
        methods.append("google")
    if user.phone_number or any(i.provider == AuthProvider.PHONE for i in identities):
        methods.append("phone")

    consent_res = await db.execute(
        select(Consent).where(Consent.user_id == user.id, Consent.revoked_at.is_(None))
    )
    active_consents = {c.consent_type: c for c in consent_res.scalars().all()}
    terms = active_consents.get(ConsentType.TERMS)
    ai_proc = active_consents.get(ConsentType.AI_DATA_PROCESSING)

    return ProfileResponse(
        user_id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        phone_number=user.phone_number,
        preferred_language=user.preferred_language or "en",
        locale=user.locale or "en-IN",
        notification_preferences=_merged_notif_prefs(user.notification_preferences),
        methods=methods,
        consent={
            "terms_accepted": terms is not None,
            "ai_data_processing_consent": ai_proc is not None,
            "consent_version": terms.consent_version if terms else "v1.0",
        },
        deletion_requested_at=user.deletion_requested_at.isoformat() if user.deletion_requested_at else None,
        deletion_scheduled_for=user.deletion_scheduled_for.isoformat() if user.deletion_scheduled_for else None,
        created_at=user.created_at.isoformat(),
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Return the authenticated user's profile, preferences, sign-in methods, and consent summary."""
    return await _build_profile_response(user, db)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    req: ProfileUpdateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update display name, preferred language, locale, and notification preferences.

    Email and phone number cannot be modified here; use link/verify flows with step-up re-auth.
    """
    updated_fields: list[str] = []
    if req.full_name is not None:
        cleaned_name = " ".join(req.full_name.strip().split())
        if not cleaned_name or len(cleaned_name) > 100:
            raise ValidationException("Display name must be between 1 and 100 characters.")
        if not DISPLAY_NAME_PATTERN.match(cleaned_name):
            raise ValidationException("Display name contains disallowed characters.")
        user.full_name = cleaned_name
        updated_fields.append("full_name")
    if req.preferred_language is not None:
        user.preferred_language = req.preferred_language
        updated_fields.append("preferred_language")
    if req.locale is not None:
        cleaned_locale = req.locale.strip()
        if not LOCALE_PATTERN.match(cleaned_locale):
            raise ValidationException("Locale must follow BCP-47 format (e.g. en-IN, ml-IN).")
        user.locale = cleaned_locale
        updated_fields.append("locale")
    if req.notification_preferences is not None:
        unknown = set(req.notification_preferences.keys()) - ALLOWED_NOTIFICATION_KEYS
        if unknown:
            raise ValidationException(f"Unsupported notification preference keys: {', '.join(sorted(unknown))}")
        merged = _merged_notif_prefs(user.notification_preferences)
        merged.update({k: bool(val) for k, val in req.notification_preferences.items()})
        user.notification_preferences = merged
        updated_fields.append("notification_preferences")

    if updated_fields:
        db.add(
            AuditTrail(
                user_id=user.id,
                actor="user",
                action="profile_updated",
                resource_type="users",
                resource_id=str(user.id),
                metadata_json={"updated_fields": updated_fields},
            )
        )
        await db.commit()
        await db.refresh(user)

    return await _build_profile_response(user, db)


@router.post("/export")
async def export_my_data(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """DPDP Data Portability export of the authenticated user's own data (secrets excluded)."""
    consents = (await db.execute(select(Consent).where(Consent.user_id == user.id))).scalars().all()
    identities = (await db.execute(select(UserIdentity).where(UserIdentity.user_id == user.id))).scalars().all()
    sessions = (await db.execute(select(UserSession).where(UserSession.user_id == user.id))).scalars().all()
    accounts = (await db.execute(select(Account).where(Account.user_id == user.id))).scalars().all()
    transactions = (await db.execute(select(Transaction).where(Transaction.user_id == user.id))).scalars().all()
    recurring = (
        (await db.execute(select(RecurringCommitment).where(RecurringCommitment.user_id == user.id)))
        .scalars()
        .all()
    )
    borrow = (await db.execute(select(BorrowAssessment).where(BorrowAssessment.user_id == user.id))).scalars().all()
    scam_logs = (await db.execute(select(ScamCheckLog).where(ScamCheckLog.user_id == user.id))).scalars().all()
    conversations = (await db.execute(select(Conversation).where(Conversation.user_id == user.id))).scalars().all()
    conv_ids = [c.id for c in conversations]
    messages = (
        (await db.execute(select(Message).where(Message.conversation_id.in_(conv_ids)))).scalars().all()
        if conv_ids
        else []
    )
    nw_items = (await db.execute(select(NetWorthItem).where(NetWorthItem.user_id == user.id))).scalars().all()
    nw_snapshots = (
        (await db.execute(select(NetWorthSnapshot).where(NetWorthSnapshot.user_id == user.id))).scalars().all()
    )

    db.add(
        AuditTrail(
            user_id=user.id,
            actor="user",
            action="dpdp_data_export",
            resource_type="users",
            resource_id=str(user.id),
            metadata_json={"exported_at": datetime.now(UTC).isoformat()},
        )
    )
    await db.commit()

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "user_id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "preferred_language": user.preferred_language,
            "locale": user.locale,
            "notification_preferences": _merged_notif_prefs(user.notification_preferences),
            "created_at": user.created_at.isoformat(),
        },
        "consents": [
            {
                "consent_type": c.consent_type.value,
                "consent_version": c.consent_version,
                "granted_at": c.granted_at.isoformat(),
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in consents
        ],
        "sign_in_methods": [
            {"provider": i.provider.value, "linked_at": i.created_at.isoformat()} for i in identities
        ],
        "sessions": [
            {
                "session_id": str(s.id),
                "is_revoked": s.is_revoked,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in sessions
        ],
        "accounts": [
            {
                "id": str(a.id),
                "name": a.name,
                "account_type": a.account_type.value,
                "currency": a.currency,
                "reported_balance": str(a.reported_balance) if a.reported_balance is not None else None,
            }
            for a in accounts
        ],
        "transactions": [
            {
                "id": str(t.id),
                "amount": str(t.amount),
                "transaction_type": t.transaction_type.value,
                "category": t.category,
                "transaction_date": t.transaction_date.isoformat(),
            }
            for t in transactions
        ],
        "recurring_commitments": [
            {"id": str(r.id), "name": r.name, "is_active": r.is_active} for r in recurring
        ],
        "borrow_assessments": [
            {"id": str(b.id), "readiness_band": b.readiness_band.value, "created_at": b.created_at.isoformat()}
            for b in borrow
        ],
        "scam_checks": [
            {"id": str(s.id), "risk_tier": s.risk_tier.value, "created_at": s.created_at.isoformat()}
            for s in scam_logs
        ],
        "conversations": [
            {"id": str(c.id), "title": c.title, "created_at": c.created_at.isoformat()} for c in conversations
        ],
        "messages": [
            {
                "id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "role": m.role.value,
                "content_masked": m.content_masked,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "net_worth_items": [
            {
                "id": str(i.id),
                "name": i.name,
                "item_type": i.item_type,
                "category": i.category,
                "amount_paise": i.amount_paise,
                "valued_at": i.valued_at.isoformat(),
                "created_at": i.created_at.isoformat(),
            }
            for i in nw_items
        ],
        "net_worth_snapshots": [
            {
                "id": str(s.id),
                "snapshot_date": s.snapshot_date.isoformat(),
                "total_assets_paise": s.total_assets_paise,
                "total_liabilities_paise": s.total_liabilities_paise,
                "net_worth_paise": s.net_worth_paise,
                "created_at": s.created_at.isoformat(),
            }
            for s in nw_snapshots
        ],
    }


@router.delete("", response_model=DeleteAccountResponse)
async def request_account_deletion(
    request: Request,
    user: User = Depends(require_recent_auth(600)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeleteAccountResponse:
    """DPDP Erasure: requires step-up re-auth, revokes all sessions, purges conversations,

    anonymizes audit identifiers, and schedules final deletion after the configured grace period.
    """
    now = datetime.now(UTC)
    grace_days = max(1, settings.account_deletion_grace_days)
    scheduled_for = now + timedelta(days=grace_days)

    user.deletion_requested_at = now
    user.deletion_scheduled_for = scheduled_for

    # 1. Revoke all active sessions
    await db.execute(update(UserSession).where(UserSession.user_id == user.id).values(is_revoked=True))

    # 2. Purge conversations & messages
    conv_ids = (await db.execute(select(Conversation.id).where(Conversation.user_id == user.id))).scalars().all()
    if conv_ids:
        await db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await db.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))

    # 2b. Purge sensitive net worth & subscription leak decisions
    await db.execute(delete(NetWorthSnapshot).where(NetWorthSnapshot.user_id == user.id))
    await db.execute(delete(NetWorthItem).where(NetWorthItem.user_id == user.id))
    await db.execute(delete(SubscriptionLeakDecision).where(SubscriptionLeakDecision.user_id == user.id))

    # 3. Anonymize audit identifiers
    await db.execute(
        update(AuditTrail).where(AuditTrail.user_id == user.id).values(user_id=None, metadata_json={"anonymized": True})
    )
    await db.execute(
        update(AuthAuditLog)
        .where(AuthAuditLog.user_id == user.id)
        .values(user_id=None, identifier_hash=None, ip_address_mask=None, user_agent=None, metadata_json=None)
    )

    client_ip = request.client.host if request.client else None
    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.LOGOUT_ALL,
        user_id=None,
        ip_address=client_ip,
        user_agent=None,
        metadata={"reason": "dpdp_account_deletion_requested"},
    )
    await db.commit()

    return DeleteAccountResponse(
        status="deletion_scheduled",
        deletion_requested_at=now.isoformat(),
        deletion_scheduled_for=scheduled_for.isoformat(),
        grace_period_days=grace_days,
        message=(
            f"Account deletion scheduled for {scheduled_for.strftime('%Y-%m-%d %H:%M UTC')}. "
            "You can cancel this request before the grace period ends."
        ),
    )


@router.post("/delete/cancel", response_model=ProfileResponse)
async def cancel_account_deletion(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Cancel a scheduled account deletion while within the grace period."""
    now = datetime.now(UTC)
    if user.deletion_scheduled_for is None:
        raise ConflictException("No pending account deletion request found.")
    sched = (
        user.deletion_scheduled_for.replace(tzinfo=UTC)
        if user.deletion_scheduled_for.tzinfo is None
        else user.deletion_scheduled_for
    )
    if sched <= now:
        raise ConflictException("The deletion grace period has already expired.")

    user.deletion_requested_at = None
    user.deletion_scheduled_for = None
    db.add(
        AuditTrail(
            user_id=user.id,
            actor="user",
            action="account_deletion_cancelled",
            resource_type="users",
            resource_id=str(user.id),
            metadata_json={"cancelled_at": now.isoformat()},
        )
    )
    await db.commit()
    await db.refresh(user)
    return await _build_profile_response(user, db)
