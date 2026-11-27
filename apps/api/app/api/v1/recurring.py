import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_consent
from app.core.errors import BadRequestException, ConflictException, NotFoundException
from app.models.enums import AuditActor, ConsentType, TransactionType
from app.models.plan import Transaction
from app.models.protect import AuditTrail
from app.models.recurring import (
    RecurringCommitment,
    RecurringNotification,
    RecurringOccurrence,
)
from app.models.user import User
from app.services.recurring_service import (
    detect_suggested_recurring,
    evaluate_overdue_occurrences,
    generate_due_notifications,
    generate_schedule,
    get_bill_reminders,
    match_transaction_to_occurrence,
    replenish_recurring_occurrences,
)

router = APIRouter(prefix="/recurring", tags=["Recurring Payments & Commitments"])


class DeclareCommitmentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, json_schema_extra={"example": "House Rent"})
    category: str = Field("Rent & Housing", json_schema_extra={"example": "Rent & Housing"})
    amount_type: Literal["fixed", "variable_band"] = Field("fixed", json_schema_extra={"example": "fixed"})
    expected_amount: float = Field(..., gt=0, json_schema_extra={"example": 15000.0})
    min_amount: float | None = Field(None, gt=0, json_schema_extra={"example": 14000.0})
    max_amount: float | None = Field(None, gt=0, json_schema_extra={"example": 16000.0})
    frequency: Literal["weekly", "monthly", "quarterly", "yearly"] = Field(
        "monthly", json_schema_extra={"example": "monthly"}
    )
    due_rule_day: int = Field(..., ge=1, le=31, json_schema_extra={"example": 5})
    merchant: str | None = Field(None, json_schema_extra={"example": "Landlord"})
    merchant_keywords: list[str] | None = Field(default=None)
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    origin: Literal["declared", "suggested_confirmed"] = Field(default="declared")


class UpdateCommitmentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None)
    amount_type: Literal["fixed", "variable_band"] | None = Field(default=None)
    expected_amount: float | None = Field(default=None, gt=0)
    min_amount: float | None = Field(default=None, gt=0)
    max_amount: float | None = Field(default=None, gt=0)
    frequency: Literal["weekly", "monthly", "quarterly", "yearly"] | None = Field(default=None)
    due_rule_day: int | None = Field(default=None, ge=1, le=31)
    merchant: str | None = Field(default=None)
    merchant_keywords: list[str] | None = Field(default=None)
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    expected_version: int | None = Field(default=None, ge=1)


class CommitmentResponse(BaseModel):
    id: str
    user_id: str
    name: str
    category: str
    amount_type: str
    expected_amount: float
    min_amount: float | None
    max_amount: float | None
    frequency: str
    due_rule_day: int
    merchant: str | None
    merchant_keywords: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    version: int = 1
    is_active: bool
    origin: str
    created_at: str


class OccurrenceResponse(BaseModel):
    id: str
    commitment_id: str
    commitment_name: str
    category: str
    due_date: str
    expected_amount: float
    status: str
    paid_date: str | None
    paid_amount: float | None
    match_reason: str | None = None
    mismatch_flag: str | None = None
    mismatch_reason: str | None = None


class NotificationResponse(BaseModel):
    id: str
    occurrence_id: str
    notification_type: str
    channel: str
    title: str
    message: str
    is_read: bool
    sent_at: str


def _serialize_commitment(c: RecurringCommitment) -> CommitmentResponse:
    return CommitmentResponse(
        id=str(c.id),
        user_id=str(c.user_id),
        name=c.name,
        category=c.category,
        amount_type=c.amount_type,
        expected_amount=float(c.expected_amount),
        min_amount=float(c.min_amount) if c.min_amount is not None else None,
        max_amount=float(c.max_amount) if c.max_amount is not None else None,
        frequency=c.frequency,
        due_rule_day=c.due_rule_day,
        merchant=c.merchant,
        merchant_keywords=list(c.merchant_keywords) if c.merchant_keywords else None,
        start_date=c.start_date.isoformat() if c.start_date else None,
        end_date=c.end_date.isoformat() if c.end_date else None,
        version=c.version,
        is_active=c.is_active,
        origin=c.origin,
        created_at=c.created_at.isoformat(),
    )


@router.post("/commitments", response_model=CommitmentResponse, status_code=201)
async def declare_commitment(
    req: DeclareCommitmentRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> CommitmentResponse:
    """Declare a recurring commitment (e.g. Rent, EMI, Subscription) and generate schedule. Requires terms consent."""
    if req.end_date and req.start_date and req.end_date < req.start_date:
        raise BadRequestException("end_date cannot be earlier than start_date")
    if req.min_amount is not None and req.max_amount is not None and req.min_amount > req.max_amount:
        raise BadRequestException("min_amount cannot exceed max_amount")

    commitment = RecurringCommitment(
        user_id=current_user.id,
        name=req.name.strip(),
        category=req.category,
        amount_type=req.amount_type,
        expected_amount=Decimal(str(req.expected_amount)),
        min_amount=Decimal(str(req.min_amount)) if req.min_amount is not None else None,
        max_amount=Decimal(str(req.max_amount)) if req.max_amount is not None else None,
        frequency=req.frequency,
        due_rule_day=req.due_rule_day,
        merchant=req.merchant.strip() if req.merchant else None,
        merchant_keywords=[k.strip() for k in req.merchant_keywords if k.strip()] if req.merchant_keywords else None,
        start_date=req.start_date,
        end_date=req.end_date,
        is_active=True,
        origin=req.origin,
    )
    db.add(commitment)
    await db.flush()

    occurrences = generate_schedule(
        commitment_id=commitment.id,
        user_id=current_user.id,
        due_rule_day=commitment.due_rule_day,
        expected_amount=commitment.expected_amount,
        frequency=commitment.frequency,
        start_date=commitment.start_date,
        end_date=commitment.end_date,
        count=3,
    )
    for occ in occurrences:
        db.add(occ)

    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="recurring_commitment_created",
            resource_type="recurring_commitment",
            resource_id=str(commitment.id),
            metadata_json={"frequency": commitment.frequency, "origin": commitment.origin},
        )
    )
    await db.commit()
    await db.refresh(commitment)

    return _serialize_commitment(commitment)


@router.get("/commitments", response_model=list[CommitmentResponse])
async def list_commitments(
    include_paused: bool = False,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[CommitmentResponse]:
    """List recurring commitments for the authenticated user."""
    stmt = select(RecurringCommitment).where(RecurringCommitment.user_id == current_user.id)
    if not include_paused:
        stmt = stmt.where(RecurringCommitment.is_active.is_(True))
    stmt = stmt.order_by(RecurringCommitment.due_rule_day.asc())
    result = await db.execute(stmt)
    commitments = result.scalars().all()

    return [_serialize_commitment(c) for c in commitments]


@router.patch("/commitments/{commitment_id}", response_model=CommitmentResponse)
async def update_commitment(
    commitment_id: str,
    req: UpdateCommitmentRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> CommitmentResponse:
    """Update or pause/resume a recurring commitment with optimistic concurrency and cross-user 404 isolation."""
    try:
        c_uuid = uuid.UUID(commitment_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Commitment not found") from err

    stmt = select(RecurringCommitment).where(
        RecurringCommitment.id == c_uuid,
        RecurringCommitment.user_id == current_user.id,
    )
    res = await db.execute(stmt)
    commitment = res.scalar_one_or_none()
    if not commitment:
        raise NotFoundException("Commitment not found")

    if req.expected_version is not None and req.expected_version != commitment.version:
        raise ConflictException("Commitment was modified concurrently. Please reload and retry.")

    if req.name is not None:
        commitment.name = req.name.strip()
    if req.category is not None:
        commitment.category = req.category
    if req.amount_type is not None:
        commitment.amount_type = req.amount_type
    if req.expected_amount is not None:
        commitment.expected_amount = Decimal(str(req.expected_amount))
    if req.min_amount is not None:
        commitment.min_amount = Decimal(str(req.min_amount))
    if req.max_amount is not None:
        commitment.max_amount = Decimal(str(req.max_amount))
    if req.frequency is not None:
        commitment.frequency = req.frequency
    if req.due_rule_day is not None:
        commitment.due_rule_day = req.due_rule_day
    if req.merchant is not None:
        commitment.merchant = req.merchant.strip()
    if req.merchant_keywords is not None:
        commitment.merchant_keywords = [k.strip() for k in req.merchant_keywords if k.strip()]
    if req.start_date is not None:
        commitment.start_date = req.start_date
    if req.end_date is not None:
        commitment.end_date = req.end_date
    if req.is_active is not None:
        commitment.is_active = req.is_active
    commitment.version += 1

    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="recurring_commitment_updated",
            resource_type="recurring_commitment",
            resource_id=str(commitment.id),
            metadata_json={"version": commitment.version, "is_active": commitment.is_active},
        )
    )
    await db.commit()
    await db.refresh(commitment)
    return _serialize_commitment(commitment)


@router.delete("/commitments/{commitment_id}", status_code=204)
async def delete_commitment(
    commitment_id: str,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deactivate a recurring commitment."""
    try:
        c_uuid = uuid.UUID(commitment_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Commitment not found") from err

    stmt = select(RecurringCommitment).where(
        RecurringCommitment.id == c_uuid,
        RecurringCommitment.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    commitment = result.scalar_one_or_none()
    if not commitment:
        raise NotFoundException("Commitment not found")

    commitment.is_active = False
    stmt_cancel = select(RecurringOccurrence).where(
        RecurringOccurrence.commitment_id == commitment.id,
        RecurringOccurrence.status == "upcoming",
    )
    res_cancel = await db.execute(stmt_cancel)
    canceled_occurrences = res_cancel.scalars().all()
    canceled_ids = [occ.id for occ in canceled_occurrences]
    for occ in canceled_occurrences:
        occ.status = "cancelled"
    if canceled_ids:
        await db.execute(delete(RecurringNotification).where(RecurringNotification.occurrence_id.in_(canceled_ids)))
    await db.commit()


@router.post("/sync")
async def sync_recurring_lifecycle(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Synchronize recurring occurrences: mark overdue, generate reminders, replenish schedule."""
    overdue = await evaluate_overdue_occurrences(db=db, user_id=current_user.id)
    notifs = await generate_due_notifications(db=db, user_id=current_user.id)
    replenished = await replenish_recurring_occurrences(db=db, user_id=current_user.id)
    await db.commit()
    return {
        "status": "synchronized",
        "overdue_marked": len(overdue),
        "notifications_generated": len(notifs),
        "occurrences_replenished": len(replenished),
    }


@router.get("/occurrences", response_model=list[OccurrenceResponse])
async def list_occurrences(
    status: Literal["upcoming", "paid", "missed", "overdue", "cancelled"] | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[OccurrenceResponse]:
    """List recurring payment occurrences (upcoming, paid, missed, overdue)."""
    stmt = (
        select(RecurringOccurrence, RecurringCommitment)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(RecurringOccurrence.user_id == current_user.id)
        .order_by(RecurringOccurrence.due_date.asc())
    )
    if status:
        stmt = stmt.where(RecurringOccurrence.status == status.lower())

    result = await db.execute(stmt)
    records = result.all()

    return [
        OccurrenceResponse(
            id=str(occ.id),
            commitment_id=str(comm.id),
            commitment_name=comm.name,
            category=comm.category,
            due_date=occ.due_date.isoformat(),
            expected_amount=float(occ.expected_amount),
            status=occ.status,
            paid_date=occ.paid_date.isoformat() if occ.paid_date else None,
            paid_amount=float(occ.paid_amount) if occ.paid_amount is not None else None,
            match_reason=occ.match_reason,
            mismatch_flag=occ.mismatch_flag,
            mismatch_reason=occ.mismatch_reason,
        )
        for occ, comm in records
    ]


@router.get("/reminders")
async def list_bill_reminders(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deterministically compute due_soon (7d) and overdue bill reminders in IST."""
    await evaluate_overdue_occurrences(db=db, user_id=current_user.id)
    reminders = await get_bill_reminders(db=db, user_id=current_user.id)
    await db.commit()
    return reminders


@router.post("/match")
async def run_recurring_matching(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Match imported debit transactions against active recurring commitments and flag mismatches."""
    tx_stmt = (
        select(Transaction)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == TransactionType.DEBIT,
            Transaction.is_recurring.is_(False),
        )
        .order_by(Transaction.transaction_date.asc())
    )
    tx_res = await db.execute(tx_stmt)
    txs = tx_res.scalars().all()
    matched = 0
    for tx in txs:
        occ = await match_transaction_to_occurrence(db=db, user_id=current_user.id, transaction=tx)
        if occ is not None:
            matched += 1
    await db.commit()
    return {"matched_count": matched}


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationResponse]:
    """Retrieve recurring payment alert notifications for the user's inbox."""
    stmt = (
        select(RecurringNotification)
        .where(RecurringNotification.user_id == current_user.id)
        .order_by(RecurringNotification.sent_at.desc())
    )
    if unread_only:
        stmt = stmt.where(RecurringNotification.is_read.is_(False))

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    return [
        NotificationResponse(
            id=str(n.id),
            occurrence_id=str(n.occurrence_id),
            notification_type=n.notification_type,
            channel=n.channel,
            title=n.title,
            message=n.message_masked,
            is_read=n.is_read,
            sent_at=n.sent_at.isoformat(),
        )
        for n in notifications
    ]


@router.patch("/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Mark an in-app notification as read."""
    try:
        n_uuid = uuid.UUID(notification_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Notification not found") from err

    stmt = select(RecurringNotification).where(
        RecurringNotification.id == n_uuid,
        RecurringNotification.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise NotFoundException("Notification not found")

    notif.is_read = True
    await db.commit()


@router.get("/suggestions")
async def get_recurring_suggestions(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Scan past transaction history to suggest candidate recurring payments with regular intervals."""
    stmt = (
        select(Transaction).where(Transaction.user_id == current_user.id).order_by(Transaction.transaction_date.asc())
    )
    result = await db.execute(stmt)
    txs = result.scalars().all()

    tx_dicts = [
        {
            "merchant": t.merchant or t.normalized_merchant,
            "amount": float(t.amount),
            "date": t.transaction_date,
            "transaction_type": t.transaction_type.value,
            "category": t.category,
        }
        for t in txs
    ]
    return detect_suggested_recurring(tx_dicts)
