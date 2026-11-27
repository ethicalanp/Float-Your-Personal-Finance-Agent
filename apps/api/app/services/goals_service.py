import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.budget import BudgetPlan
from app.models.goals import EmergencyFundConfig, Goal
from app.models.plan import Account
from app.models.recurring import RecurringCommitment
from app.services.budget_service import IST_TZ, get_ist_month

ESSENTIAL_RECURRING_CATEGORIES = {"rent", "rent & housing", "emi", "loan", "utilities", "insurance"}


class GoalItemOut(BaseModel):
    id: str
    name: str
    target_amount_paise: int
    saved_paise: int
    over_saved_paise: int
    remaining_paise: int
    target_date: str
    priority: int
    version: int
    months_remaining: int
    is_past_due: bool
    is_funded: bool
    suggested_monthly_paise: int
    allocated_monthly_paise: int
    feasible: bool
    progress_pct: float


class GoalsOverviewResponse(BaseModel):
    ist_month: str
    budget_savings_paise: int | None
    total_suggested_monthly_paise: int
    has_allocation_conflict: bool
    shortfall_paise: int
    goals: list[GoalItemOut] = Field(default_factory=list)


class EmergencyFundResponse(BaseModel):
    ist_month: str
    target_months: int
    needs_paise: int
    essential_recurring_paise: int
    essential_monthly_paise: int
    target_amount_paise: int
    saved_paise: int
    liquid_accounts_paise: int
    effective_saved_paise: int
    over_saved_paise: int
    remaining_paise: int
    progress_pct: float
    version: int


async def _exec(session: AsyncSession | Session, stmt: Any) -> Any:
    if isinstance(session, AsyncSession):
        return await session.execute(stmt)
    return session.execute(stmt)


def get_ist_today(now_utc: datetime | None = None) -> date:
    ref = now_utc or datetime.now(UTC)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)
    return ref.astimezone(IST_TZ).date()


def compute_months_remaining(target_date: date, today_ist: date) -> tuple[int, bool]:
    """Return (months_remaining, is_past_due) using IST calendar months."""
    is_past = target_date < today_ist
    raw_months = (target_date.year - today_ist.year) * 12 + (target_date.month - today_ist.month)
    return max(0, raw_months), is_past


def suggested_monthly_largest_remainder(remaining_paise: int, months: int) -> int:
    """Compute monthly savings in paise using largest-remainder integer division."""
    if remaining_paise <= 0:
        return 0
    if months <= 0:
        return remaining_paise
    base = remaining_paise // months
    rem = remaining_paise % months
    return base + (1 if rem > 0 else 0)


def allocate_budget_across_goals(demands: list[int], budget_paise: int) -> list[int]:
    """Allocate budget_paise across goals in priority order, with exact largest-remainder if capped."""
    if budget_paise <= 0 or not demands:
        return [0] * len(demands)
    total_demand = sum(demands)
    if total_demand <= budget_paise:
        return list(demands)

    # Priority-first allocation so higher-priority goals remain feasible and user sees exact conflict
    remaining = budget_paise
    allocs = [0] * len(demands)
    for i, d in enumerate(demands):
        give = min(d, remaining)
        allocs[i] = give
        remaining -= give
    return allocs


def _monthly_equivalent_paise(c: RecurringCommitment) -> int:
    amt = int(round(float(c.expected_amount or 0) * 100))
    if c.frequency == "weekly":
        return int(round(amt * 52 / 12))
    if c.frequency == "quarterly":
        return int(round(amt / 3))
    if c.frequency == "yearly":
        return int(round(amt / 12))
    return amt


async def compute_goals_overview(
    session: AsyncSession | Session,
    user_id: uuid.UUID,
    month: str | None = None,
    now_utc: datetime | None = None,
) -> GoalsOverviewResponse:
    today_ist = get_ist_today(now_utc)
    target_month = month or get_ist_month(now_utc)

    bp_res = await _exec(
        session,
        select(BudgetPlan).where(
            BudgetPlan.user_id == user_id,
            BudgetPlan.month == target_month,
            BudgetPlan.is_current.is_(True),
        ),
    )
    plan: BudgetPlan | None = bp_res.scalar_one_or_none()
    budget_savings_paise = int(plan.savings_paise) if plan is not None else None

    g_res = await _exec(
        session,
        select(Goal)
        .where(Goal.user_id == user_id)
        .order_by(Goal.priority.asc(), Goal.target_date.asc(), Goal.created_at.asc()),
    )
    goals = list(g_res.scalars().all())

    demands: list[int] = []
    prelim: list[dict[str, Any]] = []
    for g in goals:
        target_p = int(g.target_amount_paise)
        saved_p = int(g.saved_paise)
        over_p = max(0, saved_p - target_p)
        rem_p = max(0, target_p - saved_p)
        months, is_past = compute_months_remaining(g.target_date, today_ist)
        sug_p = suggested_monthly_largest_remainder(rem_p, months)
        progress = min(100.0, round((saved_p / target_p) * 100.0, 1)) if target_p > 0 else 100.0
        demands.append(sug_p)
        prelim.append(
            {
                "g": g,
                "target_p": target_p,
                "saved_p": saved_p,
                "over_p": over_p,
                "rem_p": rem_p,
                "months": months,
                "is_past": is_past,
                "sug_p": sug_p,
                "progress": progress,
            }
        )

    total_suggested = sum(demands)
    if budget_savings_paise is not None:
        allocs = allocate_budget_across_goals(demands, budget_savings_paise)
        has_conflict = total_suggested > budget_savings_paise
        shortfall = max(0, total_suggested - budget_savings_paise)
    else:
        allocs = list(demands)
        has_conflict = False
        shortfall = 0

    out_items: list[GoalItemOut] = []
    for item, alloc_p in zip(prelim, allocs, strict=True):
        g = item["g"]
        sug_p = item["sug_p"]
        feasible = (budget_savings_paise is None) or (sug_p == 0) or (alloc_p >= sug_p)
        out_items.append(
            GoalItemOut(
                id=str(g.id),
                name=g.name,
                target_amount_paise=item["target_p"],
                saved_paise=item["saved_p"],
                over_saved_paise=item["over_p"],
                remaining_paise=item["rem_p"],
                target_date=g.target_date.isoformat(),
                priority=int(g.priority),
                version=int(g.version),
                months_remaining=item["months"],
                is_past_due=item["is_past"],
                is_funded=item["rem_p"] == 0,
                suggested_monthly_paise=sug_p,
                allocated_monthly_paise=alloc_p,
                feasible=feasible,
                progress_pct=item["progress"],
            )
        )

    return GoalsOverviewResponse(
        ist_month=target_month,
        budget_savings_paise=budget_savings_paise,
        total_suggested_monthly_paise=total_suggested,
        has_allocation_conflict=has_conflict,
        shortfall_paise=shortfall,
        goals=out_items,
    )


async def compute_emergency_fund_overview(
    session: AsyncSession | Session,
    user_id: uuid.UUID,
    month: str | None = None,
    now_utc: datetime | None = None,
) -> EmergencyFundResponse:
    target_month = month or get_ist_month(now_utc)

    cfg_res = await _exec(
        session,
        select(EmergencyFundConfig).where(EmergencyFundConfig.user_id == user_id),
    )
    cfg: EmergencyFundConfig | None = cfg_res.scalar_one_or_none()
    target_months = int(cfg.target_months) if cfg is not None else 6
    saved_paise = int(cfg.saved_paise) if cfg is not None else 0
    version = int(cfg.version) if cfg is not None else 0

    bp_res = await _exec(
        session,
        select(BudgetPlan).where(
            BudgetPlan.user_id == user_id,
            BudgetPlan.month == target_month,
            BudgetPlan.is_current.is_(True),
        ),
    )
    plan: BudgetPlan | None = bp_res.scalar_one_or_none()
    needs_paise = int(plan.needs_paise) if plan is not None else 0

    rec_res = await _exec(
        session,
        select(RecurringCommitment).where(
            RecurringCommitment.user_id == user_id,
            RecurringCommitment.is_active.is_(True),
        ),
    )
    commitments = list(rec_res.scalars().all())
    essential_rec_paise = sum(
        _monthly_equivalent_paise(c)
        for c in commitments
        if (c.category or "").strip().lower() in ESSENTIAL_RECURRING_CATEGORIES
    )

    essential_monthly_paise = needs_paise + essential_rec_paise
    target_amount_paise = target_months * essential_monthly_paise

    acc_res = await _exec(session, select(Account).where(Account.user_id == user_id))
    accounts = list(acc_res.scalars().all())
    liquid_accounts_paise = sum(
        int(round(float(a.reported_balance or 0.0) * 100))
        for a in accounts
        if str(a.account_type.value if hasattr(a.account_type, "value") else a.account_type)
        in ("savings", "checking")
    )

    effective_saved = saved_paise + liquid_accounts_paise
    over_saved = max(0, effective_saved - target_amount_paise)
    remaining = max(0, target_amount_paise - effective_saved)
    progress = (
        min(100.0, round((effective_saved / target_amount_paise) * 100.0, 1))
        if target_amount_paise > 0
        else 100.0
    )

    return EmergencyFundResponse(
        ist_month=target_month,
        target_months=target_months,
        needs_paise=needs_paise,
        essential_recurring_paise=essential_rec_paise,
        essential_monthly_paise=essential_monthly_paise,
        target_amount_paise=target_amount_paise,
        saved_paise=saved_paise,
        liquid_accounts_paise=liquid_accounts_paise,
        effective_saved_paise=effective_saved,
        over_saved_paise=over_saved,
        remaining_paise=remaining,
        progress_pct=progress,
        version=version,
    )
