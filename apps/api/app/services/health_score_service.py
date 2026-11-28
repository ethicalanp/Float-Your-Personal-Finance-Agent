import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.borrow import BorrowAssessment
from app.models.budget import DEFAULT_CATEGORY_MAPPINGS, BudgetPlan
from app.models.enums import AuditActor, TransactionType
from app.models.plan import Account, Transaction
from app.models.protect import AuditTrail
from app.models.recurring import RecurringCommitment
from app.models.user import User
from app.services.budget_service import get_ist_month, get_ist_month_bounds

FORMULA_VERSION = "v1.0.0"

COMPONENT_WEIGHTS: dict[str, int] = {
    "savings_rate": 25,
    "emergency_fund_months": 20,
    "debt_to_income": 20,
    "budget_adherence": 15,
    "subscriptions_share": 10,
    "insurance_flag": 10,
}

HEALTH_DISCLAIMER = (
    "Educational financial health indicator only — not personalized financial, investment, "
    "tax, or insurance product advice."
)


class HealthScoreComponent(BaseModel):
    key: str
    label: str
    status: Literal["available", "insufficient_data"]
    score: int | None = None
    weight: int
    value_display: str
    why: str
    educational_tip: str


class FloatPathStep(BaseModel):
    priority: int
    pillar: Literal["Protect", "Plan", "Borrow-ready"]
    title: str
    why: str
    href: str


class HealthScoreHistoryPoint(BaseModel):
    recorded_at: str
    score: int | None = None
    band: str
    formula_version: str


class HealthScoreResponse(BaseModel):
    formula_version: str
    month: str
    overall_score: int | None = None
    band: Literal["strong", "steady", "building", "needs_attention", "insufficient_data"]
    confidence: Literal["high", "medium", "low"]
    available_components: int
    total_components: int = 6
    has_essential_insurance: bool | None = None
    components: list[HealthScoreComponent] = Field(default_factory=list)
    best_next_action: FloatPathStep | None = None
    float_path: list[FloatPathStep] = Field(default_factory=list)
    history: list[HealthScoreHistoryPoint] = Field(default_factory=list)
    delta_from_previous: int | None = None
    version_changed: bool = False
    disclaimer: str = HEALTH_DISCLAIMER


async def _exec(session: AsyncSession | Session, stmt: Any) -> Any:
    if isinstance(session, AsyncSession):
        return await session.execute(stmt)
    return session.execute(stmt)


def _score_band(score: int | None) -> Literal["strong", "steady", "building", "needs_attention", "insufficient_data"]:
    if score is None:
        return "insufficient_data"
    if score >= 80:
        return "strong"
    if score >= 60:
        return "steady"
    if score >= 40:
        return "building"
    return "needs_attention"


def _monthly_equivalent_paise(c: RecurringCommitment) -> int:
    amt = int(round(float(c.expected_amount or 0) * 100))
    if c.frequency == "weekly":
        return int(round(amt * 52 / 12))
    if c.frequency == "quarterly":
        return int(round(amt / 3))
    if c.frequency == "yearly":
        return int(round(amt / 12))
    return amt


def _score_savings_rate(rate_pct: float) -> int:
    if rate_pct >= 20.0:
        return 100
    if rate_pct >= 10.0:
        return int(round(60.0 + ((rate_pct - 10.0) / 10.0) * 40.0))
    if rate_pct >= 0.0:
        return int(round(20.0 + (rate_pct / 10.0) * 40.0))
    return 0


def _score_emergency_months(months: float) -> int:
    if months >= 6.0:
        return 100
    if months >= 3.0:
        return int(round(70.0 + ((months - 3.0) / 3.0) * 30.0))
    if months >= 1.0:
        return int(round(35.0 + ((months - 1.0) / 2.0) * 35.0))
    return max(0, int(round(months * 35.0)))


def _score_dti(dti_pct: float) -> int:
    if dti_pct <= 15.0:
        return 100
    if dti_pct <= 35.0:
        return int(round(100.0 - ((dti_pct - 15.0) / 20.0) * 40.0))
    if dti_pct <= 50.0:
        return int(round(60.0 - ((dti_pct - 35.0) / 15.0) * 35.0))
    return 0


def _score_budget_adherence(ratio: float) -> int:
    if ratio <= 0.95:
        return 100
    if ratio <= 1.05:
        return 75
    if ratio <= 1.20:
        return 40
    return 10


def _score_subscriptions(sub_pct: float) -> int:
    if sub_pct <= 5.0:
        return 100
    if sub_pct <= 10.0:
        return 70
    if sub_pct <= 20.0:
        return 35
    return 10


async def compute_health_score(
    session: AsyncSession | Session,
    user: User,
    month: str | None = None,
    formula_version: str = FORMULA_VERSION,
    record_snapshot: bool = True,
) -> HealthScoreResponse:
    """Compute deterministic, explainable, versioned Float Health Score and Float Path."""
    target_month = month or get_ist_month()
    start_utc, end_utc = get_ist_month_bounds(target_month)

    # 1. Accounts (liquid balances)
    acc_res = await _exec(session, select(Account).where(Account.user_id == user.id))
    accounts = list(acc_res.scalars().all())
    liquid_accounts = [
        a
        for a in accounts
        if str(a.account_type.value if hasattr(a.account_type, "value") else a.account_type)
        in ("savings", "checking")
    ]
    liquid_balance_paise = sum(int(round(float(a.reported_balance or 0.0) * 100)) for a in liquid_accounts)

    # 2. Month transactions
    tx_res = await _exec(
        session,
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= start_utc,
            Transaction.transaction_date < end_utc,
        ),
    )
    month_txs = list(tx_res.scalars().all())
    inflow_paise = sum(
        int(round(float(t.amount) * 100)) for t in month_txs if t.transaction_type == TransactionType.CREDIT
    )
    outflow_paise = sum(
        int(round(float(t.amount) * 100)) for t in month_txs if t.transaction_type == TransactionType.DEBIT
    )

    # 3. Budget plan
    bp_res = await _exec(
        session,
        select(BudgetPlan).where(
            BudgetPlan.user_id == user.id,
            BudgetPlan.month == target_month,
            BudgetPlan.is_current.is_(True),
        ),
    )
    plan: BudgetPlan | None = bp_res.scalar_one_or_none()

    # 4. Active recurring commitments
    rec_res = await _exec(
        session,
        select(RecurringCommitment).where(
            RecurringCommitment.user_id == user.id,
            RecurringCommitment.is_active.is_(True),
        ),
    )
    commitments = list(rec_res.scalars().all())

    # 5. Borrow assessment existence
    borrow_res = await _exec(
        session,
        select(BorrowAssessment).where(BorrowAssessment.user_id == user.id).limit(1),
    )
    has_borrow = borrow_res.scalar_one_or_none() is not None

    # Effective monthly income (prefer positive cash-flow inflow, else declared budget income)
    plan_income_paise = int(plan.monthly_income_paise) + int(plan.extra_income_paise) if plan is not None else 0
    income_paise = inflow_paise if inflow_paise > 0 else plan_income_paise

    # User-entered insurance flag from notification_preferences JSON
    prefs = user.notification_preferences or {}
    raw_ins = prefs.get("has_essential_insurance")
    has_ins: bool | None = raw_ins if isinstance(raw_ins, bool) else None

    components: list[HealthScoreComponent] = []

    # Component 1: Savings Rate (weight 25)
    if income_paise > 0 and (inflow_paise > 0 or outflow_paise > 0):
        savings_rate_pct = ((income_paise - outflow_paise) / income_paise) * 100.0
        s_score = _score_savings_rate(savings_rate_pct)
        components.append(
            HealthScoreComponent(
                key="savings_rate",
                label="Savings Rate",
                status="available",
                score=s_score,
                weight=COMPONENT_WEIGHTS["savings_rate"],
                value_display=f"{savings_rate_pct:.1f}%",
                why=f"Net cash flow this month is {savings_rate_pct:.1f}% of monthly income.",
                educational_tip="Aiming to retain 20% or more of monthly income builds steady resilience.",
            )
        )
    else:
        components.append(
            HealthScoreComponent(
                key="savings_rate",
                label="Savings Rate",
                status="insufficient_data",
                score=None,
                weight=COMPONENT_WEIGHTS["savings_rate"],
                value_display="Insufficient data",
                why="Monthly income and transaction cash flow are needed to measure savings rate.",
                educational_tip="Upload a recent bank statement or set your monthly income in Plan.",
            )
        )

    # Component 2: Emergency-Fund Months (weight 20)
    monthly_expense_base = outflow_paise if outflow_paise > 0 else (int(plan.needs_paise) if plan is not None else 0)
    if liquid_accounts and liquid_balance_paise > 0 and monthly_expense_base > 0:
        ef_months = liquid_balance_paise / monthly_expense_base
        ef_score = _score_emergency_months(ef_months)
        components.append(
            HealthScoreComponent(
                key="emergency_fund_months",
                label="Emergency-Fund Months",
                status="available",
                score=ef_score,
                weight=COMPONENT_WEIGHTS["emergency_fund_months"],
                value_display=f"{ef_months:.1f} mo",
                why=f"Liquid savings cover approximately {ef_months:.1f} months of current monthly outflow.",
                educational_tip="Educational benchmark: 3 to 6 months of essential expenses in liquid savings.",
            )
        )
    else:
        components.append(
            HealthScoreComponent(
                key="emergency_fund_months",
                label="Emergency-Fund Months",
                status="insufficient_data",
                score=None,
                weight=COMPONENT_WEIGHTS["emergency_fund_months"],
                value_display="Insufficient data",
                why="Needs both positive liquid account balance and monthly expense baseline.",
                educational_tip="Add your savings account balance and upload a statement to compute buffer months.",
            )
        )

    # Component 3: Debt-to-Income (EMI / income) (weight 20)
    emi_paise = sum(
        _monthly_equivalent_paise(c)
        for c in commitments
        if "emi" in (c.category or "").lower() or "loan" in (c.category or "").lower()
    )
    if income_paise > 0 and (commitments or month_txs):
        dti_pct = (emi_paise / income_paise) * 100.0
        dti_score = _score_dti(dti_pct)
        components.append(
            HealthScoreComponent(
                key="debt_to_income",
                label="Debt-to-Income (EMI)",
                status="available",
                score=dti_score,
                weight=COMPONENT_WEIGHTS["debt_to_income"],
                value_display=f"{dti_pct:.1f}%",
                why=f"Active EMI commitments represent {dti_pct:.1f}% of monthly income.",
                educational_tip="Keeping total EMIs below 35% of take-home income preserves borrowing headroom.",
            )
        )
    else:
        components.append(
            HealthScoreComponent(
                key="debt_to_income",
                label="Debt-to-Income (EMI)",
                status="insufficient_data",
                score=None,
                weight=COMPONENT_WEIGHTS["debt_to_income"],
                value_display="Insufficient data",
                why="Requires monthly income plus transaction or recurring EMI records.",
                educational_tip="Set income in Plan and declare any EMIs under Recurring & bills.",
            )
        )

    # Component 4: Budget Adherence (weight 15)
    if plan is not None and month_txs:
        mappings = plan.category_mappings or dict(DEFAULT_CATEGORY_MAPPINGS)
        actual_spend = 0
        for t in month_txs:
            if t.transaction_type != TransactionType.DEBIT or t.category == "Transfers":
                continue
            bucket = mappings.get(t.category or "Other", "wants")
            if bucket in ("needs", "wants"):
                actual_spend += int(round(float(t.amount) * 100))
        planned_spend = int(plan.needs_paise) + int(plan.wants_paise)
        if planned_spend > 0:
            ratio = actual_spend / planned_spend
            ba_score = _score_budget_adherence(ratio)
            components.append(
                HealthScoreComponent(
                    key="budget_adherence",
                    label="Budget Adherence",
                    status="available",
                    score=ba_score,
                    weight=COMPONENT_WEIGHTS["budget_adherence"],
                    value_display=f"{ratio * 100:.0f}%",
                    why=f"Actual Needs+Wants spending is {ratio * 100:.0f}% of your planned budget cap.",
                    educational_tip="Tracking weekly outflows keeps Needs and Wants within your target split.",
                )
            )
        else:
            components.append(
                HealthScoreComponent(
                    key="budget_adherence",
                    label="Budget Adherence",
                    status="insufficient_data",
                    score=None,
                    weight=COMPONENT_WEIGHTS["budget_adherence"],
                    value_display="Insufficient data",
                    why="Planned Needs+Wants allocation is zero.",
                    educational_tip="Update your monthly budget split in Plan.",
                )
            )
    else:
        components.append(
            HealthScoreComponent(
                key="budget_adherence",
                label="Budget Adherence",
                status="insufficient_data",
                score=None,
                weight=COMPONENT_WEIGHTS["budget_adherence"],
                value_display="Insufficient data",
                why="Requires both a monthly budget plan and imported transactions for this month.",
                educational_tip="Configure your 50/30/20 plan and upload transactions to compare plan vs actual.",
            )
        )

    # Component 5: Subscriptions Share (weight 10)
    sub_paise = sum(
        _monthly_equivalent_paise(c)
        for c in commitments
        if "sub" in (c.category or "").lower()
    )
    if income_paise > 0 and (commitments or month_txs):
        sub_pct = (sub_paise / income_paise) * 100.0
        sub_score = _score_subscriptions(sub_pct)
        components.append(
            HealthScoreComponent(
                key="subscriptions_share",
                label="Subscriptions Share",
                status="available",
                score=sub_score,
                weight=COMPONENT_WEIGHTS["subscriptions_share"],
                value_display=f"{sub_pct:.1f}%",
                why=f"Recurring subscriptions account for {sub_pct:.1f}% of monthly income.",
                educational_tip="Review unused subscriptions regularly to free up monthly savings.",
            )
        )
    else:
        components.append(
            HealthScoreComponent(
                key="subscriptions_share",
                label="Subscriptions Share",
                status="insufficient_data",
                score=None,
                weight=COMPONENT_WEIGHTS["subscriptions_share"],
                value_display="Insufficient data",
                why="Requires monthly income and recurring/transaction records.",
                educational_tip="Add recurring subscriptions in Plan to monitor fixed leaks.",
            )
        )

    # Component 6: Insurance Flag (user-entered) (weight 10)
    if has_ins is not None:
        ins_score = 100 if has_ins else 25
        components.append(
            HealthScoreComponent(
                key="insurance_flag",
                label="Essential Insurance",
                status="available",
                score=ins_score,
                weight=COMPONENT_WEIGHTS["insurance_flag"],
                value_display="Covered" if has_ins else "Not covered",
                why=(
                    "You confirmed active essential health/term protection."
                    if has_ins
                    else "You indicated essential health or term protection is not yet in place."
                ),
                educational_tip="Basic health/term protection helps shield emergency savings from medical shocks.",
            )
        )
    else:
        components.append(
            HealthScoreComponent(
                key="insurance_flag",
                label="Essential Insurance",
                status="insufficient_data",
                score=None,
                weight=COMPONENT_WEIGHTS["insurance_flag"],
                value_display="Insufficient data",
                why="Self-reported insurance status has not been set yet.",
                educational_tip="Set your essential insurance status below (educational tracking only).",
            )
        )

    # Aggregate over available components only (missing data never scored as 0)
    avail = [c for c in components if c.status == "available" and c.score is not None]
    avail_count = len(avail)
    if avail_count == 0:
        overall_score: int | None = None
        confidence: Literal["high", "medium", "low"] = "low"
    else:
        total_w = sum(c.weight for c in avail)
        overall_score = int(round(sum((c.score or 0) * c.weight for c in avail) / total_w))
        confidence = "high" if avail_count >= 5 else ("medium" if avail_count >= 3 else "low")

    band = _score_band(overall_score)

    # Build ordered Float Path across Plan, Protect, Borrow-ready
    path: list[FloatPathStep] = []
    comp_map = {c.key: c for c in components}

    if plan is None or not month_txs:
        path.append(
            FloatPathStep(
                priority=len(path) + 1,
                pillar="Plan",
                title="Set monthly budget & upload statement",
                why="Unlocks savings rate, emergency buffer, and budget adherence tracking.",
                href="/plan",
            )
        )
    if comp_map["insurance_flag"].status == "insufficient_data" or (comp_map["insurance_flag"].score or 0) < 100:
        path.append(
            FloatPathStep(
                priority=len(path) + 1,
                pillar="Protect",
                title="Confirm essential protection status",
                why="Verifying health/term coverage helps guard against unexpected medical expenses.",
                href="/home#health-score",
            )
        )
    if comp_map["emergency_fund_months"].status == "available" and (comp_map["emergency_fund_months"].score or 0) < 70:
        path.append(
            FloatPathStep(
                priority=len(path) + 1,
                pillar="Plan",
                title="Grow emergency buffer toward 3–6 months",
                why="Your current liquid balance is under 3 months of monthly outflow.",
                href="/plan",
            )
        )
    if (comp_map["subscriptions_share"].score or 100) < 70 or (comp_map["budget_adherence"].score or 100) < 75:
        path.append(
            FloatPathStep(
                priority=len(path) + 1,
                pillar="Plan",
                title="Review recurring bills & subscriptions",
                why="Trimming unused recurring charges improves monthly cash-flow headroom.",
                href="/recurring",
            )
        )
    if not has_borrow or (comp_map["debt_to_income"].score or 100) < 60:
        path.append(
            FloatPathStep(
                priority=len(path) + 1,
                pillar="Borrow-ready",
                title="Check indicative borrow readiness",
                why="See your non-CIBIL debt-to-income and cash-flow stability signals.",
                href="/borrow",
            )
        )
    path.append(
        FloatPathStep(
            priority=len(path) + 1,
            pillar="Protect",
            title="Keep digital payment & 1930 fraud safety active",
            why="Verify suspicious links or SMS messages before acting on urgent requests.",
            href="/protect",
        )
    )
    # Re-index priorities 1..N
    for i, step in enumerate(path, start=1):
        step.priority = i

    best_next = path[0] if path else None

    # Fetch snapshot history from AuditTrail
    hist_stmt = (
        select(AuditTrail)
        .where(
            AuditTrail.user_id == user.id,
            AuditTrail.resource_type == "health_score_snapshot",
        )
        .order_by(AuditTrail.created_at.desc())
        .limit(10)
    )
    hist_res = await _exec(session, hist_stmt)
    hist_rows = list(hist_res.scalars().all())

    history: list[HealthScoreHistoryPoint] = []
    for row in hist_rows:
        meta = row.metadata_json or {}
        history.append(
            HealthScoreHistoryPoint(
                recorded_at=str(meta.get("recorded_at") or row.created_at.isoformat()),
                score=meta.get("score"),
                band=str(meta.get("band") or "insufficient_data"),
                formula_version=str(meta.get("formula_version") or "v1.0.0"),
            )
        )

    delta_from_prev: int | None = None
    version_changed = False
    if history:
        prev = history[0]
        if prev.formula_version != formula_version:
            version_changed = True
        elif overall_score is not None and prev.score is not None:
            delta_from_prev = overall_score - prev.score

    # Record new snapshot if requested and score/version/band changed from latest
    should_record = record_snapshot and overall_score is not None and (
        not history
        or history[0].score != overall_score
        or history[0].formula_version != formula_version
        or history[0].band != band
    )
    if should_record:
        now_iso = datetime.now(UTC).isoformat()
        snap = AuditTrail(
            id=uuid.uuid4(),
            user_id=user.id,
            actor=AuditActor.USER,
            action="health_score_snapshot",
            resource_type="health_score_snapshot",
            resource_id=f"{target_month}:{formula_version}",
            metadata_json={
                "formula_version": formula_version,
                "score": overall_score,
                "band": band,
                "available_components": avail_count,
                "recorded_at": now_iso,
            },
        )
        session.add(snap)
        if isinstance(session, AsyncSession):
            await session.flush()
        else:
            session.flush()
        history.insert(
            0,
            HealthScoreHistoryPoint(
                recorded_at=now_iso,
                score=overall_score,
                band=band,
                formula_version=formula_version,
            ),
        )

    return HealthScoreResponse(
        formula_version=formula_version,
        month=target_month,
        overall_score=overall_score,
        band=band,
        confidence=confidence,
        available_components=avail_count,
        has_essential_insurance=has_ins,
        components=components,
        best_next_action=best_next,
        float_path=path,
        history=history,
        delta_from_previous=delta_from_prev,
        version_changed=version_changed,
    )
