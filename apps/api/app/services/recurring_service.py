import calendar
import math
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Transaction
from app.models.recurring import (
    RecurringCommitment,
    RecurringNotification,
    RecurringOccurrence,
)

IST_TZ = ZoneInfo("Asia/Kolkata")


def get_ist_today() -> date:
    """Return today's date in Asia/Kolkata (IST)."""
    return datetime.now(IST_TZ).date()


def get_due_date_for_month(year: int, month: int, day: int) -> date:
    """Calculate valid date handling month-end bounds (e.g. Feb 28/29, April 30)."""
    max_days = calendar.monthrange(year, month)[1]
    safe_day = min(max(day, 1), max_days)
    return date(year, month, safe_day)


def generate_schedule(
    commitment_id: uuid.UUID,
    user_id: uuid.UUID,
    due_rule_day: int,
    expected_amount: Decimal,
    frequency: str = "monthly",
    start_date: date | None = None,
    end_date: date | None = None,
    count: int = 3,
) -> list[RecurringOccurrence]:
    """Generate upcoming occurrences for a commitment across weekly, monthly, quarterly, or yearly intervals."""
    start = start_date or get_ist_today()
    occurrences: list[RecurringOccurrence] = []
    freq_lower = frequency.lower().strip()

    if freq_lower == "weekly":
        for i in range(count):
            due = start + timedelta(days=7 * i)
            if end_date is not None and due > end_date:
                break
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

    month_steps = {"monthly": 1, "quarterly": 3, "yearly": 12}
    try:
        month_step = month_steps[freq_lower]
    except KeyError as err:
        raise ValueError(f"Unsupported recurring frequency: {frequency}") from err

    for i in range(count + 1):
        month_offset = start.month + (i * month_step)
        target_year = start.year + (month_offset - 1) // 12
        target_month = ((month_offset - 1) % 12) + 1

        due = get_due_date_for_month(target_year, target_month, due_rule_day)
        if due < start:
            continue
        if end_date is not None and due > end_date:
            break
        occurrences.append(
            RecurringOccurrence(
                commitment_id=commitment_id,
                user_id=user_id,
                due_date=due,
                expected_amount=expected_amount,
                status="upcoming",
            )
        )
        if len(occurrences) >= count:
            break

    return occurrences


def _extract_keywords(comm: RecurringCommitment) -> list[str]:
    kws: list[str] = []
    if comm.merchant:
        kws.append(comm.merchant.strip().lower())
    if comm.merchant_keywords:
        for kw in comm.merchant_keywords:
            cleaned = str(kw).strip().lower()
            if cleaned and cleaned not in kws:
                kws.append(cleaned)
    if not kws and comm.name:
        kws.append(comm.name.strip().lower())
    return [k for k in kws if k]


def _merchant_match_score(txn: Transaction, comm: RecurringCommitment) -> tuple[int, str | None]:
    """Return (score, matched_keyword). 0 means no match."""
    haystack = " ".join(
        filter(
            None,
            [
                txn.normalized_merchant,
                txn.merchant,
                txn.description_cleaned,
                txn.description,
            ],
        )
    ).lower()
    if not haystack:
        return 0, None

    keywords = _extract_keywords(comm)
    best_score = 0
    best_kw: str | None = None
    txn_merchant_lower = (txn.normalized_merchant or txn.merchant or "").strip().lower()

    for kw in keywords:
        if txn_merchant_lower and txn_merchant_lower == kw:
            return 100, kw
        if kw in haystack:
            score = 80 if len(kw) >= 4 else 60
            if score > best_score:
                best_score = score
                best_kw = kw
    return best_score, best_kw


def _within_date_window(txn_date: date, due_date: date, window_days: int) -> tuple[bool, int]:
    """Check date window including weekend drift (Sat/Sun due date -> Mon)."""
    effective_max = due_date + timedelta(days=window_days)
    if due_date.weekday() == 5:  # Saturday -> allow through Monday + window
        effective_max = max(effective_max, due_date + timedelta(days=2 + window_days))
    elif due_date.weekday() == 6:  # Sunday -> allow through Monday + window
        effective_max = max(effective_max, due_date + timedelta(days=1 + window_days))
    effective_min = due_date - timedelta(days=window_days)
    delta = abs((txn_date - due_date).days)
    return (effective_min <= txn_date <= effective_max), delta


def _amount_matches(actual: Decimal, comm: RecurringCommitment, occ: RecurringOccurrence, tol_pct: Decimal) -> bool:
    if comm.amount_type == "variable_band" and comm.min_amount is not None and comm.max_amount is not None:
        return comm.min_amount <= actual <= comm.max_amount
    expected = occ.expected_amount
    tolerance = max(expected * tol_pct, Decimal("100.00"))
    return abs(actual - expected) <= tolerance


def _match_transaction_against_rows(
    transaction: Transaction,
    rows: Sequence[tuple[RecurringOccurrence, RecurringCommitment]],
    txn_date: date,
    date_window_days: int,
    amount_tolerance_pct: Decimal,
) -> RecurringOccurrence | None:
    """Match a single debit transaction against pre-fetched (occurrence, commitment) rows."""
    scored_matches: list[tuple[tuple[int, Decimal, int], RecurringOccurrence, RecurringCommitment, str]] = []
    for occ, comm in rows:
        if comm.start_date and txn_date < comm.start_date:
            continue
        if comm.end_date and txn_date > comm.end_date:
            continue

        m_score, matched_kw = _merchant_match_score(transaction, comm)
        if m_score == 0 or matched_kw is None:
            continue

        in_window, date_delta = _within_date_window(txn_date, occ.due_date, date_window_days)
        if not in_window:
            continue

        if occ.status == "paid":
            if _amount_matches(transaction.amount, comm, occ, amount_tolerance_pct):
                occ.mismatch_flag = "duplicate"
                occ.mismatch_reason = f"Duplicate debit of ₹{transaction.amount:.2f} for already-paid occurrence"
            continue

        if occ.status != "upcoming":
            continue

        if not _amount_matches(transaction.amount, comm, occ, amount_tolerance_pct):
            occ.mismatch_flag = "amount_high" if transaction.amount > occ.expected_amount else "amount_mismatch"
            occ.mismatch_reason = f"Charged ₹{transaction.amount:.2f} vs expected ₹{occ.expected_amount:.2f}"
            continue

        amt_diff = abs(transaction.amount - occ.expected_amount)
        scored_matches.append(((m_score, -amt_diff, -date_delta), occ, comm, matched_kw))

    if not scored_matches:
        return None

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    _, best_occ, best_comm, best_kw = scored_matches[0]
    best_occ.status = "paid"
    best_occ.matched_transaction_id = transaction.id
    best_occ.paid_date = txn_date
    best_occ.paid_amount = transaction.amount
    best_occ.match_reason = (
        f"Matched '{best_kw}' ({best_comm.name}) within tolerance and date window"
    )
    best_occ.mismatch_flag = None
    best_occ.mismatch_reason = None
    transaction.is_recurring = True
    return best_occ


async def match_transactions_bulk(
    db: AsyncSession,
    user_id: uuid.UUID,
    transactions: Sequence[Transaction],
    date_window_days: int = 4,
    amount_tolerance_pct: Decimal = Decimal("0.05"),
) -> int:
    """Match a batch of debit transactions against recurring occurrences using a single DB query."""
    debit_pairs: list[tuple[Transaction, date]] = []
    for tx in transactions:
        if tx.transaction_type.value.lower() != "debit":
            continue
        tx_dt = tx.transaction_date
        if tx_dt.tzinfo is None:
            tx_dt = tx_dt.replace(tzinfo=timezone.utc)
        debit_pairs.append((tx, tx_dt.astimezone(IST_TZ).date()))

    if not debit_pairs:
        return 0

    min_date = min(d for _, d in debit_pairs) - timedelta(days=date_window_days + 3)
    max_date = max(d for _, d in debit_pairs) + timedelta(days=date_window_days + 3)
    stmt = (
        select(RecurringOccurrence, RecurringCommitment)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(
            RecurringOccurrence.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
            RecurringOccurrence.due_date >= min_date,
            RecurringOccurrence.due_date <= max_date,
        )
    )
    result = await db.execute(stmt)
    rows = [(occ, comm) for occ, comm in result.all()]
    if not rows:
        return 0

    matched_count = 0
    for tx, txn_date in debit_pairs:
        if _match_transaction_against_rows(tx, rows, txn_date, date_window_days, amount_tolerance_pct) is not None:
            matched_count += 1
    return matched_count


async def match_transaction_to_occurrence(
    db: AsyncSession,
    user_id: uuid.UUID,
    transaction: Transaction,
    date_window_days: int = 4,
    amount_tolerance_pct: Decimal = Decimal("0.05"),
) -> RecurringOccurrence | None:
    """Tag a debit transaction as expected only when merchant + amount + date window (incl. weekend drift) match."""
    if transaction.transaction_type.value.lower() != "debit":
        return None

    tx_dt = transaction.transaction_date
    if tx_dt.tzinfo is None:
        tx_dt = tx_dt.replace(tzinfo=timezone.utc)
    txn_date = tx_dt.astimezone(IST_TZ).date()
    min_date = txn_date - timedelta(days=date_window_days + 3)
    max_date = txn_date + timedelta(days=date_window_days + 3)

    stmt = (
        select(RecurringOccurrence, RecurringCommitment)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(
            RecurringOccurrence.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
            RecurringOccurrence.due_date >= min_date,
            RecurringOccurrence.due_date <= max_date,
        )
    )
    result = await db.execute(stmt)
    rows = [(occ, comm) for occ, comm in result.all()]
    return _match_transaction_against_rows(transaction, rows, txn_date, date_window_days, amount_tolerance_pct)


async def evaluate_overdue_occurrences(
    db: AsyncSession,
    user_id: uuid.UUID,
    as_of: date | None = None,
    grace_period_days: int = 3,
) -> list[RecurringOccurrence]:
    """Identify upcoming occurrences that passed due date + grace period without a match and mark missed."""
    now_date = as_of or get_ist_today()
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
        occ.mismatch_flag = "missed"
        occ.mismatch_reason = "No matching debit within grace window"

    return list(overdue_list)


async def get_bill_reminders(
    db: AsyncSession,
    user_id: uuid.UUID,
    as_of: date | None = None,
    due_soon_days: int = 7,
) -> dict[str, list[dict[str, Any]]]:
    """Compute deterministic due_soon and overdue bill reminders in IST."""
    today = as_of or get_ist_today()
    soon_end = today + timedelta(days=due_soon_days)

    stmt = (
        select(RecurringOccurrence, RecurringCommitment)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(
            RecurringOccurrence.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
            RecurringOccurrence.status.in_(["upcoming", "overdue", "missed"]),
        )
        .order_by(RecurringOccurrence.due_date.asc())
    )
    res = await db.execute(stmt)
    due_soon: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []

    for occ, comm in res.all():
        item = {
            "occurrence_id": str(occ.id),
            "commitment_id": str(comm.id),
            "name": comm.name,
            "category": comm.category,
            "due_date": occ.due_date.isoformat(),
            "expected_amount": float(occ.expected_amount),
            "status": "overdue" if occ.due_date < today and occ.status == "upcoming" else occ.status,
            "days_delta": (occ.due_date - today).days,
            "mismatch_flag": occ.mismatch_flag,
            "mismatch_reason": occ.mismatch_reason,
        }
        if occ.due_date < today or occ.status in ("overdue", "missed"):
            overdue.append(item)
        elif today <= occ.due_date <= soon_end:
            due_soon.append(item)

    return {"due_soon": due_soon, "overdue": overdue}


def filter_unusual_spend_transactions(transactions: list[Transaction]) -> list[Transaction]:
    """Exclude expected recurring debits from unusual-spend and subscription-leak alerts."""
    return [t for t in transactions if not t.is_recurring]


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
        effective_end = min(horizon_end, comm.end_date) if comm.end_date else horizon_end
        effective_start = max(now_date, comm.start_date) if comm.start_date else now_date

        if freq_lower == "weekly":
            for i in range(16):
                due = effective_start + timedelta(days=7 * i)
                if due > effective_end:
                    break
                if due >= effective_start and due not in existing_due_dates:
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
            continue

        month_steps = {"monthly": 1, "quarterly": 3, "yearly": 12}
        try:
            month_step = month_steps[freq_lower]
        except KeyError as err:
            raise ValueError(f"Unsupported recurring frequency: {comm.frequency}") from err

        current_year = effective_start.year
        current_month = effective_start.month

        for i in range(24):
            offset = (current_month - 1) + (i * month_step)
            target_year = current_year + offset // 12
            target_month = (offset % 12) + 1

            due = get_due_date_for_month(target_year, target_month, comm.due_rule_day)
            if due > effective_end:
                break
            if due >= effective_start and due not in existing_due_dates:
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
