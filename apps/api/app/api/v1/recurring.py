import uuid
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_consent
from app.core.errors import NotFoundException
from app.models.enums import ConsentType
from app.models.plan import Transaction
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
    replenish_recurring_occurrences,
)

router = APIRouter(prefix="/recurring", tags=["Recurring Payments & Commitments"])


class DeclareCommitmentRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "House Rent"})
    category: str = Field("Rent & Housing", json_schema_extra={"example": "Rent & Housing"})
    amount_type: Literal["fixed", "variable_band"] = Field("fixed", json_schema_extra={"example": "fixed"})
    expected_amount: float = Field(..., gt=0, json_schema_extra={"example": 15000.0})
    min_amount: float | None = Field(None, json_schema_extra={"example": 14000.0})
    max_amount: float | None = Field(None, json_schema_extra={"example": 16000.0})
    frequency: Literal["monthly", "quarterly", "yearly"] = Field("monthly", json_schema_extra={"example": "monthly"})
    due_rule_day: int = Field(..., ge=1, le=31, json_schema_extra={"example": 5})
    merchant: str | None = Field(None, json_schema_extra={"example": "Landlord"})


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


class NotificationResponse(BaseModel):
    id: str
    occurrence_id: str
    notification_type: str
    channel: str
    title: str
    message: str
    is_read: bool
    sent_at: str


@router.post("/commitments", response_model=CommitmentResponse, status_code=201)
async def declare_commitment(
    req: DeclareCommitmentRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> CommitmentResponse:
    """Declare a recurring commitment (e.g. Rent, EMI, Subscription) and generate schedule. Requires terms consent."""
    commitment = RecurringCommitment(
        user_id=current_user.id,
        name=req.name,
        category=req.category,
        amount_type=req.amount_type,
        expected_amount=Decimal(str(req.expected_amount)),
        min_amount=Decimal(str(req.min_amount)) if req.min_amount is not None else None,
        max_amount=Decimal(str(req.max_amount)) if req.max_amount is not None else None,
        frequency=req.frequency,
        due_rule_day=req.due_rule_day,
        merchant=req.merchant,
        is_active=True,
        origin="declared",
    )
    db.add(commitment)
    await db.flush()

    # Generate upcoming occurrences according to commitment frequency interval
    occurrences = generate_schedule(
        commitment_id=commitment.id,
        user_id=current_user.id,
        due_rule_day=commitment.due_rule_day,
        expected_amount=commitment.expected_amount,
        frequency=commitment.frequency,
        count=3,
    )
    for occ in occurrences:
        db.add(occ)

    await db.commit()
    await db.refresh(commitment)

    return CommitmentResponse(
        id=str(commitment.id),
        user_id=str(commitment.user_id),
        name=commitment.name,
        category=commitment.category,
        amount_type=commitment.amount_type,
        expected_amount=float(commitment.expected_amount),
        min_amount=float(commitment.min_amount) if commitment.min_amount is not None else None,
        max_amount=float(commitment.max_amount) if commitment.max_amount is not None else None,
        frequency=commitment.frequency,
        due_rule_day=commitment.due_rule_day,
        merchant=commitment.merchant,
        is_active=commitment.is_active,
        origin=commitment.origin,
        created_at=commitment.created_at.isoformat(),
    )


@router.get("/commitments", response_model=list[CommitmentResponse])
async def list_commitments(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[CommitmentResponse]:
    """List all active recurring commitments for the authenticated user."""
    stmt = (
        select(RecurringCommitment)
        .where(
            RecurringCommitment.user_id == current_user.id,
            RecurringCommitment.is_active.is_(True),
        )
        .order_by(RecurringCommitment.due_rule_day.asc())
    )
    result = await db.execute(stmt)
    commitments = result.scalars().all()

    return [
        CommitmentResponse(
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
            is_active=c.is_active,
            origin=c.origin,
            created_at=c.created_at.isoformat(),
        )
        for c in commitments
    ]


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
        )
        for occ, comm in records
    ]


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
