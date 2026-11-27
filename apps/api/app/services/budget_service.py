import calendar
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import DEFAULT_CATEGORY_MAPPINGS, BudgetPlan
from app.models.enums import TransactionType
from app.models.plan import Transaction
from app.models.recurring import RecurringCommitment

IST_TZ = ZoneInfo("Asia/Kolkata")
MAX_INCOME_PAISE = 10_000_000_000  # ₹100 Crore (1e8 INR = 1e10 paise)

BUDGET_PRESETS: dict[str, dict[str, Decimal]] = {
    "50_30_20": {"needs": Decimal("50.00"), "wants": Decimal("30.00"), "savings": Decimal("20.00")},
    "60_20_20": {"needs": Decimal("60.00"), "wants": Decimal("20.00"), "savings": Decimal("20.00")},
    "50_20_30": {"needs": Decimal("50.00"), "wants": Decimal("20.00"), "savings": Decimal("30.00")},
}


def get_ist_month(dt: datetime | None = None) -> str:
    """Return YYYY-MM for the given datetime (or now) in Asia/Kolkata."""
    ref = dt or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref.astimezone(IST_TZ).strftime("%Y-%m")


def get_ist_month_bounds(month: str) -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) for an IST calendar month YYYY-MM."""
    parts = month.split("-")
    if len(parts) != 2:
        raise ValueError("Month must be in YYYY-MM format")
    year, mon = int(parts[0]), int(parts[1])
    if mon < 1 or mon > 12:
        raise ValueError("Month must be between 01 and 12")
    last_day = calendar.monthrange(year, mon)[1]
    start_ist = datetime(year, mon, 1, 0, 0, 0, tzinfo=IST_TZ)
    end_ist = datetime(year, mon, last_day, 23, 59, 59, 999999, tzinfo=IST_TZ)
    return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)


def to_paise(rupees: Decimal | int | str) -> int:
    """Convert INR rupees to integer paise deterministically."""
    dec = Decimal(str(rupees)).quantize(Decimal("0.01"))
    return int(dec * 100)


def paise_to_rupees(paise: int) -> Decimal:
    """Convert integer paise to INR Decimal(0.01)."""
    return (Decimal(paise) / Decimal("100")).quantize(Decimal("0.01"))


def allocate_budget_paise(
    total_paise: int,
    needs_pct: Decimal,
    wants_pct: Decimal,
    savings_pct: Decimal,
) -> tuple[int, int, int]:
    """Allocate total_paise across needs/wants/savings using the largest-remainder method."""
    if total_paise <= 0 or total_paise > MAX_INCOME_PAISE:
        raise ValueError("Total monthly income must be > 0 and <= ₹100 crore")
    if needs_pct < 0 or wants_pct < 0 or savings_pct < 0:
        raise ValueError("Budget percentages must be >= 0")
    total_pct = (needs_pct + wants_pct + savings_pct).quantize(Decimal("0.01"))
    if total_pct != Decimal("100.00"):
        raise ValueError("Budget percentages must sum to 100.00%")

    exact_shares = [
        ("needs", Decimal(total_paise) * needs_pct / Decimal("100")),
        ("wants", Decimal(total_paise) * wants_pct / Decimal("100")),
        ("savings", Decimal(total_paise) * savings_pct / Decimal("100")),
    ]
    floors = {k: int(val) for k, val in exact_shares}
    remainders = sorted(
        [(val - Decimal(floors[k]), -idx, k) for idx, (k, val) in enumerate(exact_shares)],
        reverse=True,
    )
    leftover = total_paise - sum(floors.values())
    for i in range(leftover):
        _, _, key = remainders[i]
        floors[key] += 1

    return floors["needs"], floors["wants"], floors["savings"]


def resolve_bucket(category: str, mappings: dict[str, Any] | None = None) -> str:
    """Map a transaction or commitment category to needs/wants/savings."""
    merged = dict(DEFAULT_CATEGORY_MAPPINGS)
    if mappings:
        merged.update(mappings)
    cat_lower = category.strip().lower()
    for k, v in merged.items():
        if k.strip().lower() == cat_lower and v in ("needs", "wants", "savings"):
            return str(v)
    if cat_lower in ("rent", "emi", "utilities", "insurance"):
        return "needs"
    if cat_lower in ("sip", "savings", "investments"):
        return "savings"
    return "wants"


def _monthly_equivalent_paise(comm: RecurringCommitment) -> int:
    base = to_paise(comm.expected_amount)
    freq = comm.frequency.lower().strip()
    if freq == "weekly":
        return (base * 52) // 12
    if freq == "quarterly":
        return base // 3
    if freq == "yearly":
        return base // 12
    return base


async def compute_irregular_avg_paise(
    db: AsyncSession,
    user_id: uuid.UUID,
    months: int = 3,
    as_of_month: str | None = None,
) -> int:
    """Compute average monthly credit inflow in paise over the last N IST months."""
    ref_month = as_of_month or get_ist_month()
    year, mon = map(int, ref_month.split("-"))
    monthly_totals: list[int] = []

    for i in range(months):
        total_m = (year * 12 + (mon - 1)) - i
        y = total_m // 12
        m = (total_m % 12) + 1
        m_str = f"{y:04d}-{m:02d}"
        start_utc, end_utc = get_ist_month_bounds(m_str)
        stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.CREDIT,
            Transaction.transaction_date >= start_utc,
            Transaction.transaction_date <= end_utc,
        )
        res = await db.execute(stmt)
        txns = res.scalars().all()
        month_sum = sum(to_paise(t.amount) for t in txns if t.category != "Transfers")
        if month_sum > 0:
            monthly_totals.append(month_sum)

    if not monthly_totals:
        return 0
    return sum(monthly_totals) // len(monthly_totals)


async def compute_plan_vs_actual(
    db: AsyncSession,
    user_id: uuid.UUID,
    month: str,
    plan: BudgetPlan | None,
) -> dict[str, Any]:
    """Compare planned buckets vs actual spending from imported transactions in IST month."""
    start_utc, end_utc = get_ist_month_bounds(month)
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.transaction_date >= start_utc,
        Transaction.transaction_date <= end_utc,
    )
    res = await db.execute(stmt)
    txns = list(res.scalars().all())

    mappings = plan.category_mappings if plan else dict(DEFAULT_CATEGORY_MAPPINGS)
    actual_paise = {"needs": 0, "wants": 0, "savings": 0}
    has_transactions = len(txns) > 0

    for t in txns:
        if t.transaction_type != TransactionType.DEBIT or t.category == "Transfers":
            continue
        bucket = resolve_bucket(t.category, mappings)
        actual_paise[bucket] += to_paise(t.amount)

    # Active recurring commitments mapped to needs
    rec_stmt = select(RecurringCommitment).where(
        RecurringCommitment.user_id == user_id,
        RecurringCommitment.is_active.is_(True),
    )
    rec_res = await db.execute(rec_stmt)
    recurring_needs_paise = 0
    for comm in rec_res.scalars().all():
        if resolve_bucket(comm.category, mappings) == "needs":
            recurring_needs_paise += _monthly_equivalent_paise(comm)

    warnings: list[str] = []
    if plan is not None:
        total_income_paise = plan.monthly_income_paise + plan.extra_income_paise
        projected_needs = max(actual_paise["needs"], recurring_needs_paise)
        if recurring_needs_paise + actual_paise["needs"] > plan.needs_paise:
            warnings.append(
                "Recurring commitments plus needs spending exceed your planned needs budget."
            )
        if projected_needs > total_income_paise or (recurring_needs_paise + actual_paise["needs"] > total_income_paise):
            warnings.append(
                "Recurring commitments plus needs spending exceed your total monthly income."
            )

    return {
        "has_transactions": has_transactions,
        "transaction_count": len(txns),
        "actual_needs_paise": actual_paise["needs"],
        "actual_wants_paise": actual_paise["wants"],
        "actual_savings_paise": actual_paise["savings"],
        "recurring_needs_paise": recurring_needs_paise,
        "warnings": warnings,
    }
