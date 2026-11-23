import calendar
import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Transaction
from app.models.recurring import (
    RecurringCommitment,
    RecurringNotification,
    RecurringOccurrence,
)


def get_due_date_for_month(year: int, month: int, day: int) -> date:
    """Calculate valid date handling month-end bounds (e.g. Feb 28/29, April 30)."""
    max_days = calendar.monthrange(year, month)[1]
    safe_day = min(day, max_days)
    return date(year, month, safe_day)


def generate_schedule(
    commitment_id: uuid.UUID,
    user_id: uuid.UUID,
    due_rule_day: int,
    expected_amount: Decimal,
    frequency: str = "monthly",
    start_date: date | None = None,
    count: int = 3,
) -> list[RecurringOccurrence]:
    """Generate upcoming occurrences for a commitment across given intervals (monthly, quarterly, yearly)."""
    start = start_date or date.today()
    occurrences = []
    freq_lower = frequency.lower().strip()
    month_steps = {"monthly": 1, "quarterly": 3, "yearly": 12}
    try:
        month_step = month_steps[freq_lower]
    except KeyError as err:
        raise ValueError(f"Unsupported recurring frequency: {frequency}") from err

    for i in range(count):
        # Calculate target year and month based on frequency interval
        month_offset = start.month + (i * month_step)
        target_year = start.year + (month_offset - 1) // 12
        target_month = ((month_offset - 1) % 12) + 1

        due = get_due_date_for_month(target_year, target_month, due_rule_day)
        if due >= start:
            occurrences.append(
                RecurringOccurrence(
                    commitment_id=commitment_id,
                    user_id=user_id,
                    due_date=due,
                    expected_amount=expected_amount,
                    status="upcoming",
                )
            )

    return occurrences


async def match_transaction_to_occurrence(
    db: AsyncSession,
    user_id: uuid.UUID,
    transaction: Transaction,
    date_window_days: int = 4,
    amount_tolerance_pct: Decimal = Decimal("0.05"),
) -> RecurringOccurrence | None:
    """Correlate incoming transaction to an upcoming occurrence by date window and amount tolerance."""
    if transaction.transaction_type.value.lower() != "debit":
        return None

    txn_date = transaction.transaction_date.date()
    min_date = txn_date - timedelta(days=date_window_days)
    max_date = txn_date + timedelta(days=date_window_days)

    # Query upcoming occurrences for this user in the date range
    stmt = (
        select(RecurringOccurrence)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(
            RecurringOccurrence.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
            RecurringOccurrence.status == "upcoming",
            RecurringOccurrence.due_date >= min_date,
            RecurringOccurrence.due_date <= max_date,
        )
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    for occ in candidates:
        expected = occ.expected_amount
        actual = transaction.amount

        # Check amount match (within tolerance or within 100 INR)
        diff = abs(actual - expected)
        tolerance = max(expected * amount_tolerance_pct, Decimal("100.00"))

        if diff <= tolerance:
            # Match found! Mark occurrence paid and link transaction
            occ.status = "paid"
            occ.matched_transaction_id = transaction.id
            occ.paid_date = txn_date
            occ.paid_amount = actual
            transaction.is_recurring = True
            return occ

    return None


async def evaluate_overdue_occurrences(
    db: AsyncSession,
    user_id: uuid.UUID,
    as_of: date | None = None,
    grace_period_days: int = 3,
) -> list[RecurringOccurrence]:
    """Identify upcoming occurrences that passed due date + grace period without a match and mark missed."""
    now_date = as_of or date.today()
    cutoff_date = now_date - timedelta(days=grace_period_days)

    stmt = (
        select(RecurringOccurrence)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(
            RecurringOccurrence.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
            RecurringOccurrence.status == "upcoming",
            RecurringOccurrence.due_date < cutoff_date,
        )
    )
    result = await db.execute(stmt)
    overdue_list = result.scalars().all()

    for occ in overdue_list:
        occ.status = "missed"

    return list(overdue_list)


async def generate_due_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    as_of: date | None = None,
) -> list[RecurringNotification]:
    """Generate deduplicated in-app notifications for payments due in 3 days or 1 day."""
    now_date = as_of or date.today()
    date_3d = now_date + timedelta(days=3)
    date_1d = now_date + timedelta(days=1)

    # Query occurrences due in 1 day or 3 days
    stmt = (
        select(RecurringOccurrence, RecurringCommitment)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(
            RecurringOccurrence.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
            RecurringOccurrence.status == "upcoming",
            RecurringOccurrence.due_date.in_([date_1d, date_3d]),
        )
    )
    result = await db.execute(stmt)
    records = result.all()

    generated_notifs = []
    for occ, comm in records:
        notif_type = "upcoming_1d" if occ.due_date == date_1d else "upcoming_3d"
        days_str = "tomorrow" if occ.due_date == date_1d else "in 3 days"

        # Check existing notification to avoid duplicates
        existing_stmt = select(RecurringNotification).where(
            RecurringNotification.occurrence_id == occ.id,
            RecurringNotification.notification_type == notif_type,
            RecurringNotification.channel == "in_app",
        )
        existing_res = await db.execute(existing_stmt)
        if existing_res.scalar_one_or_none():
            continue

        due_str = occ.due_date.strftime("%d %b %Y")
        msg = f"Reminder: {comm.name} of ₹{occ.expected_amount:,.2f} is due {days_str} on {due_str}."
        notif = RecurringNotification(
            occurrence_id=occ.id,
            user_id=user_id,
            notification_type=notif_type,
            channel="in_app",
            title=f"Upcoming Payment: {comm.name}",
            message_masked=msg,
            is_read=False,
        )
        db.add(notif)
        generated_notifs.append(notif)

    return generated_notifs


async def replenish_recurring_occurrences(
    db: AsyncSession,
    user_id: uuid.UUID,
    horizon_days: int = 90,
    as_of: date | None = None,
) -> list[RecurringOccurrence]:
    """Ensure active commitments have occurrences scheduled through the horizon window."""
    now_date = as_of or date.today()
    horizon_end = now_date + timedelta(days=horizon_days)

    stmt = select(RecurringCommitment).where(
        RecurringCommitment.user_id == user_id,
        RecurringCommitment.is_active.is_(True),
    )
    result = await db.execute(stmt)
    commitments = result.scalars().all()

    newly_created: list[RecurringOccurrence] = []
    for comm in commitments:
        occ_stmt = select(RecurringOccurrence.due_date).where(
            RecurringOccurrence.commitment_id == comm.id,
        )
        occ_res = await db.execute(occ_stmt)
        existing_due_dates = set(occ_res.scalars().all())

        freq_lower = comm.frequency.lower().strip()
        month_steps = {"monthly": 1, "quarterly": 3, "yearly": 12}
        try:
            month_step = month_steps[freq_lower]
        except KeyError as err:
            raise ValueError(f"Unsupported recurring frequency: {comm.frequency}") from err

        current_year = now_date.year
        current_month = now_date.month

        for i in range(24):
            offset = (current_month - 1) + (i * month_step)
            target_year = current_year + offset // 12
            target_month = (offset % 12) + 1

            due = get_due_date_for_month(target_year, target_month, comm.due_rule_day)
            if due > horizon_end:
                break
            if due >= now_date and due not in existing_due_dates:
                new_occ = RecurringOccurrence(
                    commitment_id=comm.id,
                    user_id=user_id,
                    due_date=due,
                    expected_amount=comm.expected_amount,
                    status="upcoming",
                )
                db.add(new_occ)
                newly_created.append(new_occ)
                existing_due_dates.add(due)

    return newly_created


def detect_suggested_recurring(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scan transaction history to detect candidate recurring payments.

    Matches regular intervals >= 3 occurrences with similar amount from the same merchant.
    """
    merchant_groups = defaultdict(list)
    for t in transactions:
        merchant = (t.get("merchant") or "").strip()
        t_type = (t.get("transaction_type") or "").lower()
        if merchant and t_type == "debit":
            merchant_groups[merchant.lower()].append(t)

    suggestions = []
    for merchant_key, txs in merchant_groups.items():
        if len(txs) < 3:
            continue

        # Sort by date
        sorted_txs = sorted(txs, key=lambda x: x["date"])
        amounts = [float(x["amount"]) for x in sorted_txs]
        avg_amount = sum(amounts) / len(amounts)

        # Variance check
        variance = sum((a - avg_amount) ** 2 for a in amounts) / len(amounts)
        std_dev = math.sqrt(variance)
        if avg_amount > 0 and (std_dev / avg_amount) > 0.20:
            continue  # amount fluctuates too widely

        # Interval check between consecutive transactions (approx 25 to 35 days for monthly)
        intervals = []
        for i in range(1, len(sorted_txs)):
            d1 = sorted_txs[i - 1]["date"]
            d2 = sorted_txs[i]["date"]
            if isinstance(d1, str):
                d1 = datetime.fromisoformat(d1)
            if isinstance(d2, str):
                d2 = datetime.fromisoformat(d2)
            intervals.append((d2 - d1).days)

        avg_interval = sum(intervals) / len(intervals)
        if 25 <= avg_interval <= 35:
            # Candidate monthly recurring commitment
            latest = sorted_txs[-1]
            latest_date = latest["date"]
            if isinstance(latest_date, str):
                latest_date = datetime.fromisoformat(latest_date)
            due_day = latest_date.day

            suggestions.append(
                {
                    "merchant": merchant_key.title(),
                    "suggested_name": f"{merchant_key.title()} Subscription",
                    "category": latest.get("category", "Subscriptions"),
                    "expected_amount": round(avg_amount, 2),
                    "frequency": "monthly",
                    "due_rule_day": due_day,
                    "confidence": "high" if len(txs) >= 4 else "medium",
                    "detected_occurrences_count": len(txs),
                }
            )

    return suggestions
