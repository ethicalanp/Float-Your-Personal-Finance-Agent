from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.tools.base import (
    Fact,
    Tool,
    ToolContext,
    ToolResult,
    calculate_percentage_change,
    quantize_currency,
    quantize_percent,
)
from app.ai.tools.registry import default_registry
from app.models.borrow import BorrowAssessment
from app.models.budget import BudgetPlan
from app.models.enums import TransactionType
from app.models.plan import Transaction
from app.models.recurring import RecurringCommitment, RecurringOccurrence
from app.services.budget_service import get_ist_month, paise_to_rupees
from app.services.recurring_service import get_ist_today


async def _execute(session: AsyncSession | Session, query: Any) -> Any:
    """Execute SQLAlchemy query supporting both AsyncSession and sync Session."""
    if isinstance(session, AsyncSession):
        return await session.execute(query)
    return session.execute(query)


def _to_utc_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc)
    return start_dt, end_dt


# ============================================================================
# 1. get_spending_summary
# ============================================================================


class SpendingSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date = Field(description="Start date (inclusive) in YYYY-MM-DD format")
    end_date: date = Field(description="End date (inclusive) in YYYY-MM-DD format")


class SpendingSummaryData(BaseModel):
    start_date: date
    end_date: date
    total_spent: Decimal
    total_income: Decimal
    net_cash_flow: Decimal
    transaction_count: int
    unclassified_count: int
    unclassified_percentage: Decimal
    categories_count: int


async def handle_spending_summary(ctx: ToolContext, args: SpendingSummaryInput) -> ToolResult:
    start_dt, end_dt = _to_utc_range(args.start_date, args.end_date)
    period_str = f"{args.start_date} to {args.end_date}"

    query = select(Transaction).where(
        Transaction.user_id == ctx.user_id,
        Transaction.transaction_date >= start_dt,
        Transaction.transaction_date <= end_dt,
    )
    result = await _execute(ctx.session, query)
    txns: list[Transaction] = list(result.scalars().all())

    total_spent = Decimal("0.00")
    total_income = Decimal("0.00")
    unclassified_count = 0
    categories: set[str] = set()

    for t in txns:
        if t.category == "Transfers":
            continue

        categories.add(t.category)
        if t.category in ("Other", "Uncategorized", "uncategorized", "unknown"):
            unclassified_count += 1

        amt = Decimal(str(t.amount))
        if t.transaction_type == TransactionType.DEBIT:
            total_spent += amt
        elif t.transaction_type == TransactionType.CREDIT:
            total_income += amt

    total_spent = quantize_currency(total_spent)
    total_income = quantize_currency(total_income)
    net_cash_flow = quantize_currency(total_income - total_spent)
    txn_count = len(txns)

    unclassified_pct = (
        quantize_percent((Decimal(unclassified_count) / Decimal(txn_count)) * Decimal("100"))
        if txn_count > 0
        else Decimal("0.00")
    )

    data = SpendingSummaryData(
        start_date=args.start_date,
        end_date=args.end_date,
        total_spent=total_spent,
        total_income=total_income,
        net_cash_flow=net_cash_flow,
        transaction_count=txn_count,
        unclassified_count=unclassified_count,
        unclassified_percentage=unclassified_pct,
        categories_count=len(categories),
    )

    facts = [
        Fact(id="total_spent", label="Total Spending", value=str(total_spent), unit="INR", period=period_str),
        Fact(id="total_income", label="Total Income", value=str(total_income), unit="INR", period=period_str),
        Fact(id="net_cash_flow", label="Net Cash Flow", value=str(net_cash_flow), unit="INR", period=period_str),
        Fact(id="transaction_count", label="Transaction Count", value=str(txn_count), unit="count", period=period_str),
    ]

    warnings = []
    if unclassified_pct > Decimal("20.00"):
        warnings.append(f"{unclassified_pct}% of transactions are uncategorized, which may affect accuracy.")

    return ToolResult(
        ok=True,
        tool="get_spending_summary",
        data=data.model_dump(),
        facts=facts,
        period=period_str,
        row_count=txn_count,
        warnings=warnings,
        data_quality={"unclassified_percentage": str(unclassified_pct)},
    )


# ============================================================================
# 2. get_category_breakdown
# ============================================================================


class CategoryBreakdownInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date = Field(description="Start date (inclusive) in YYYY-MM-DD format")
    end_date: date = Field(description="End date (inclusive) in YYYY-MM-DD format")
    top_n: int = Field(default=5, ge=1, le=20, description="Number of top spending categories to return (1-20)")


class CategoryItem(BaseModel):
    category: str
    total_amount: Decimal
    percentage_of_total: Decimal
    transaction_count: int


class CategoryBreakdownData(BaseModel):
    start_date: date
    end_date: date
    total_spending: Decimal
    top_n: int
    categories: list[CategoryItem]
    other_amount: Decimal
    other_percentage: Decimal


async def handle_category_breakdown(ctx: ToolContext, args: CategoryBreakdownInput) -> ToolResult:
    start_dt, end_dt = _to_utc_range(args.start_date, args.end_date)
    period_str = f"{args.start_date} to {args.end_date}"

    query = select(Transaction).where(
        Transaction.user_id == ctx.user_id,
        Transaction.transaction_date >= start_dt,
        Transaction.transaction_date <= end_dt,
        Transaction.transaction_type == TransactionType.DEBIT,
    )
    result = await _execute(ctx.session, query)
    txns: list[Transaction] = list(result.scalars().all())

    cat_totals: dict[str, Decimal] = {}
    cat_counts: dict[str, int] = {}
    overall_spending = Decimal("0.00")

    for t in txns:
        if t.category == "Transfers":
            continue
        amt = Decimal(str(t.amount))
        cat = t.category or "Other"
        cat_totals[cat] = cat_totals.get(cat, Decimal("0.00")) + amt
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        overall_spending += amt

    overall_spending = quantize_currency(overall_spending)

    # Sort categories by total spending descending
    sorted_cats = sorted(cat_totals.items(), key=lambda kv: kv[1], reverse=True)
    top_items = sorted_cats[: args.top_n]
    remaining_items = sorted_cats[args.top_n :]

    categories_list: list[CategoryItem] = []
    facts: list[Fact] = [
        Fact(id="total_spending", label="Total Spending", value=str(overall_spending), unit="INR", period=period_str)
    ]

    for cat_name, cat_total in top_items:
        c_amt = quantize_currency(cat_total)
        pct = (
            quantize_percent((c_amt / overall_spending) * Decimal("100"))
            if overall_spending > Decimal("0.00")
            else Decimal("0.00")
        )
        categories_list.append(
            CategoryItem(
                category=cat_name,
                total_amount=c_amt,
                percentage_of_total=pct,
                transaction_count=cat_counts[cat_name],
            )
        )
        safe_id = cat_name.lower().replace(" ", "_")
        facts.append(
            Fact(
                id=f"spending_category_{safe_id}",
                label=f"Spending on {cat_name}",
                value=str(c_amt),
                unit="INR",
                period=period_str,
            )
        )
        facts.append(
            Fact(
                id=f"spending_share_{safe_id}",
                label=f"Spending share for {cat_name}",
                value=str(pct),
                unit="%",
                period=period_str,
            )
        )

    other_amount = quantize_currency(sum((kv[1] for kv in remaining_items), Decimal("0.00")))
    other_pct = (
        quantize_percent((other_amount / overall_spending) * Decimal("100"))
        if overall_spending > Decimal("0.00")
        else Decimal("0.00")
    )

    data = CategoryBreakdownData(
        start_date=args.start_date,
        end_date=args.end_date,
        total_spending=overall_spending,
        top_n=args.top_n,
        categories=categories_list,
        other_amount=other_amount,
        other_percentage=other_pct,
    )

    return ToolResult(
        ok=True,
        tool="get_category_breakdown",
        data=data.model_dump(),
        facts=facts,
        period=period_str,
        row_count=len(categories_list),
    )


# ============================================================================
# 3. compare_periods
# ============================================================================


class ComparePeriodsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_a_start: date = Field(description="Baseline period start date (YYYY-MM-DD)")
    period_a_end: date = Field(description="Baseline period end date (YYYY-MM-DD)")
    period_b_start: date = Field(description="Comparison period start date (YYYY-MM-DD)")
    period_b_end: date = Field(description="Comparison period end date (YYYY-MM-DD)")


class PeriodSummary(BaseModel):
    start_date: date
    end_date: date
    duration_days: int
    total_spent: Decimal
    total_income: Decimal
    net_cash_flow: Decimal
    transaction_count: int


class ComparePeriodsData(BaseModel):
    period_a: PeriodSummary
    period_b: PeriodSummary
    spending_difference: Decimal
    spending_percentage_change: Decimal | None
    income_difference: Decimal
    income_percentage_change: Decimal | None
    net_difference: Decimal
    duration_mismatch_warning: str | None = None


async def _summarize_period(
    ctx: ToolContext,
    start_date: date,
    end_date: date,
) -> tuple[PeriodSummary, list[Transaction]]:
    start_dt, end_dt = _to_utc_range(start_date, end_date)
    duration_days = (end_date - start_date).days + 1

    query = select(Transaction).where(
        Transaction.user_id == ctx.user_id,
        Transaction.transaction_date >= start_dt,
        Transaction.transaction_date <= end_dt,
    )
    result = await _execute(ctx.session, query)
    txns: list[Transaction] = list(result.scalars().all())

    spent = Decimal("0.00")
    income = Decimal("0.00")
    for t in txns:
        if t.category == "Transfers":
            continue
        amt = Decimal(str(t.amount))
        if t.transaction_type == TransactionType.DEBIT:
            spent += amt
        elif t.transaction_type == TransactionType.CREDIT:
            income += amt

    spent = quantize_currency(spent)
    income = quantize_currency(income)
    net = quantize_currency(income - spent)

    summary = PeriodSummary(
        start_date=start_date,
        end_date=end_date,
        duration_days=duration_days,
        total_spent=spent,
        total_income=income,
        net_cash_flow=net,
        transaction_count=len(txns),
    )
    return summary, txns


async def handle_compare_periods(ctx: ToolContext, args: ComparePeriodsInput) -> ToolResult:
    sum_a, _ = await _summarize_period(ctx, args.period_a_start, args.period_a_end)
    sum_b, _ = await _summarize_period(ctx, args.period_b_start, args.period_b_end)

    spending_diff = quantize_currency(sum_b.total_spent - sum_a.total_spent)
    spending_pct, spending_warn = calculate_percentage_change(sum_a.total_spent, sum_b.total_spent)

    income_diff = quantize_currency(sum_b.total_income - sum_a.total_income)
    income_pct, income_warn = calculate_percentage_change(sum_a.total_income, sum_b.total_income)

    net_diff = quantize_currency(sum_b.net_cash_flow - sum_a.net_cash_flow)

    warnings: list[str] = []
    duration_mismatch = None
    if abs(sum_a.duration_days - sum_b.duration_days) > 1:
        duration_mismatch = (
            f"Comparing periods of different durations ({sum_a.duration_days} days vs {sum_b.duration_days} days). "
            "Differences may be skewed."
        )
        warnings.append(duration_mismatch)

    if spending_warn:
        warnings.append(f"Spending comparison: {spending_warn}")
    if income_warn:
        warnings.append(f"Income comparison: {income_warn}")

    data = ComparePeriodsData(
        period_a=sum_a,
        period_b=sum_b,
        spending_difference=spending_diff,
        spending_percentage_change=spending_pct,
        income_difference=income_diff,
        income_percentage_change=income_pct,
        net_difference=net_diff,
        duration_mismatch_warning=duration_mismatch,
    )

    facts = [
        Fact(id="period_a_spent", label="Period A Spending", value=str(sum_a.total_spent), unit="INR"),
        Fact(id="period_b_spent", label="Period B Spending", value=str(sum_b.total_spent), unit="INR"),
        Fact(id="spending_difference", label="Spending Difference (B - A)", value=str(spending_diff), unit="INR"),
        Fact(id="period_a_income", label="Period A Income", value=str(sum_a.total_income), unit="INR"),
        Fact(id="period_b_income", label="Period B Income", value=str(sum_b.total_income), unit="INR"),
        Fact(id="income_difference", label="Income Difference (B - A)", value=str(income_diff), unit="INR"),
        Fact(id="net_difference", label="Net Cash Flow Difference (B - A)", value=str(net_diff), unit="INR"),
    ]
    if spending_pct is not None:
        facts.append(
            Fact(id="spending_pct_change", label="Spending Percentage Change", value=str(spending_pct), unit="%")
        )
    if income_pct is not None:
        facts.append(Fact(id="income_pct_change", label="Income Percentage Change", value=str(income_pct), unit="%"))

    return ToolResult(
        ok=True,
        tool="compare_periods",
        data=data.model_dump(),
        facts=facts,
        row_count=2,
        warnings=warnings,
    )


# ============================================================================
# 4. get_cash_flow
# ============================================================================


class CashFlowInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    start_date: date = Field(description="Start date (inclusive) in YYYY-MM-DD format")
    end_date: date = Field(description="End date (inclusive) in YYYY-MM-DD format")
    granularity: Literal["daily", "weekly", "monthly"] = Field(
        default="monthly", description="Aggregation bucket granularity"
    )
    bucket: Literal["daily", "weekly", "monthly"] | None = Field(
        default=None, description="Alias for granularity"
    )


class CashFlowBucket(BaseModel):
    period_label: str
    inflow: Decimal
    outflow: Decimal
    net: Decimal
    transaction_count: int


class CashFlowData(BaseModel):
    start_date: date
    end_date: date
    granularity: str
    buckets: list[CashFlowBucket]
    total_inflow: Decimal
    total_outflow: Decimal
    average_net_per_period: Decimal


async def handle_cash_flow(ctx: ToolContext, args: CashFlowInput) -> ToolResult:
    start_dt, end_dt = _to_utc_range(args.start_date, args.end_date)
    period_str = f"{args.start_date} to {args.end_date}"

    query = select(Transaction).where(
        Transaction.user_id == ctx.user_id,
        Transaction.transaction_date >= start_dt,
        Transaction.transaction_date <= end_dt,
    ).order_by(Transaction.transaction_date.asc())
    result = await _execute(ctx.session, query)
    txns: list[Transaction] = list(result.scalars().all())

    # Bucket key generator
    def bucket_key(dt: datetime) -> str:
        if args.granularity == "daily":
            return dt.strftime("%Y-%m-%d")
        if args.granularity == "weekly":
            return f"{dt.year}-W{dt.isocalendar().week:02d}"
        return dt.strftime("%Y-%m")

    buckets_inflow: dict[str, Decimal] = {}
    buckets_outflow: dict[str, Decimal] = {}
    buckets_count: dict[str, int] = {}

    for t in txns:
        if t.category == "Transfers":
            continue
        k = bucket_key(t.transaction_date)
        amt = Decimal(str(t.amount))
        buckets_count[k] = buckets_count.get(k, 0) + 1

        if t.transaction_type == TransactionType.CREDIT:
            buckets_inflow[k] = buckets_inflow.get(k, Decimal("0.00")) + amt
        elif t.transaction_type == TransactionType.DEBIT:
            buckets_outflow[k] = buckets_outflow.get(k, Decimal("0.00")) + amt

    all_keys = sorted(set(buckets_inflow.keys()) | set(buckets_outflow.keys()) | set(buckets_count.keys()))

    bucket_list: list[CashFlowBucket] = []
    total_inflow = Decimal("0.00")
    total_outflow = Decimal("0.00")

    for k in all_keys:
        inflow = quantize_currency(buckets_inflow.get(k, Decimal("0.00")))
        outflow = quantize_currency(buckets_outflow.get(k, Decimal("0.00")))
        net = quantize_currency(inflow - outflow)
        cnt = buckets_count.get(k, 0)

        total_inflow += inflow
        total_outflow += outflow

        bucket_list.append(
            CashFlowBucket(
                period_label=k,
                inflow=inflow,
                outflow=outflow,
                net=net,
                transaction_count=cnt,
            )
        )

    total_inflow = quantize_currency(total_inflow)
    total_outflow = quantize_currency(total_outflow)
    num_buckets = len(bucket_list)
    avg_net = (
        quantize_currency((total_inflow - total_outflow) / Decimal(num_buckets))
        if num_buckets > 0
        else Decimal("0.00")
    )

    data = CashFlowData(
        start_date=args.start_date,
        end_date=args.end_date,
        granularity=args.granularity,
        buckets=bucket_list,
        total_inflow=total_inflow,
        total_outflow=total_outflow,
        average_net_per_period=avg_net,
    )

    facts = [
        Fact(id="total_inflow", label="Total Cash Inflow", value=str(total_inflow), unit="INR", period=period_str),
        Fact(id="total_outflow", label="Total Cash Outflow", value=str(total_outflow), unit="INR", period=period_str),
        Fact(
            id="average_net_per_period",
            label="Average Net per Period",
            value=str(avg_net),
            unit="INR",
            period=period_str,
        ),
    ]

    if bucket_list:
        highest_bucket = max(bucket_list, key=lambda b: b.net)
        lowest_bucket = min(bucket_list, key=lambda b: b.net)
        facts.append(
            Fact(
                id="highest_net_period",
                label="Highest Net Period",
                value=f"{highest_bucket.period_label}: {highest_bucket.net}",
                unit="INR",
            )
        )
        facts.append(
            Fact(
                id="lowest_net_period",
                label="Lowest Net Period",
                value=f"{lowest_bucket.period_label}: {lowest_bucket.net}",
                unit="INR",
            )
        )

    return ToolResult(
        ok=True,
        tool="get_cash_flow",
        data=data.model_dump(),
        facts=facts,
        period=period_str,
        row_count=len(bucket_list),
    )


# ============================================================================
# 5. list_recurring_payments
# ============================================================================


class ListRecurringPaymentsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool = Field(default=True, description="Filter active recurring commitments")


class RecurringCommitmentItem(BaseModel):
    name: str
    category: str
    amount_type: str
    expected_amount: Decimal
    frequency: str
    due_rule_day: int
    merchant: str | None
    monthly_equivalent: Decimal


class ListRecurringPaymentsData(BaseModel):
    total_monthly_committed: Decimal
    active_count: int
    commitments: list[RecurringCommitmentItem]


async def handle_list_recurring(ctx: ToolContext, args: ListRecurringPaymentsInput) -> ToolResult:
    query = select(RecurringCommitment).where(
        RecurringCommitment.user_id == ctx.user_id,
        RecurringCommitment.is_active == args.is_active,
    ).order_by(RecurringCommitment.due_rule_day.asc())

    result = await _execute(ctx.session, query)
    commitments: list[RecurringCommitment] = list(result.scalars().all())

    items: list[RecurringCommitmentItem] = []
    total_monthly = Decimal("0.00")

    for c in commitments:
        exp_amt = quantize_currency(Decimal(str(c.expected_amount)))
        freq = (c.frequency or "monthly").lower()

        if freq == "monthly":
            monthly_equiv = exp_amt
        elif freq == "quarterly":
            monthly_equiv = quantize_currency(exp_amt / Decimal("3"))
        elif freq == "yearly":
            monthly_equiv = quantize_currency(exp_amt / Decimal("12"))
        else:
            monthly_equiv = exp_amt

        total_monthly += monthly_equiv
        items.append(
            RecurringCommitmentItem(
                name=c.name,
                category=c.category,
                amount_type=c.amount_type,
                expected_amount=exp_amt,
                frequency=c.frequency,
                due_rule_day=c.due_rule_day,
                merchant=c.merchant,
                monthly_equivalent=monthly_equiv,
            )
        )

    total_monthly = quantize_currency(total_monthly)

    data = ListRecurringPaymentsData(
        total_monthly_committed=total_monthly,
        active_count=len(items),
        commitments=items,
    )

    facts = [
        Fact(id="active_recurring_count", label="Active Recurring Count", value=str(len(items)), unit="count"),
        Fact(id="total_monthly_committed", label="Total Monthly Committed", value=str(total_monthly), unit="INR"),
    ]
    for idx, item in enumerate(items, 1):
        safe_name = item.name.lower().replace(" ", "_")
        facts.append(
            Fact(
                id=f"recurring_{idx}_{safe_name}",
                label=f"Recurring: {item.name}",
                value=str(item.expected_amount),
                unit="INR",
            )
        )

    return ToolResult(
        ok=True,
        tool="list_recurring_payments",
        data=data.model_dump(),
        facts=facts,
        row_count=len(items),
    )


# ============================================================================
# 6. get_borrow_readiness
# ============================================================================


class BorrowReadinessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh: bool = Field(default=False, description="Flag indicating whether to request a refresh")


class BorrowReadinessData(BaseModel):
    status: Literal["available", "insufficient_data", "unavailable"]
    readiness_band: str | None = None
    top_factors: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[Any] = Field(default_factory=list)
    explanation: str
    model_version: str | None = None


async def handle_borrow_readiness(ctx: ToolContext, args: BorrowReadinessInput) -> ToolResult:
    query = (
        select(BorrowAssessment)
        .where(BorrowAssessment.user_id == ctx.user_id)
        .order_by(BorrowAssessment.created_at.desc())
        .limit(1)
    )
    result = await _execute(ctx.session, query)
    assessment: BorrowAssessment | None = result.scalars().first()

    if assessment is None:
        data = BorrowReadinessData(
            status="insufficient_data",
            readiness_band=None,
            top_factors=[],
            recommendations=[],
            explanation=(
                "No borrow readiness assessment has been computed yet for this account. "
                "Borrow readiness answers are indicative only."
            ),
            model_version=None,
        )
        return ToolResult(
            ok=True,
            tool="get_borrow_readiness",
            data=data.model_dump(),
            facts=[],
            row_count=0,
            warnings=["No borrow readiness model assessment on file."],
        )

    band_val = (
        assessment.readiness_band.value
        if hasattr(assessment.readiness_band, "value")
        else str(assessment.readiness_band)
    )

    data = BorrowReadinessData(
        status="available",
        readiness_band=band_val,
        top_factors=assessment.top_factors or [],
        recommendations=assessment.recommendations or [],
        explanation=f"Indicative borrow readiness is assessed as '{band_val}'.",
        model_version=assessment.model_version,
    )

    facts = [
        Fact(id="readiness_band", label="Indicative Readiness Band", value=band_val, unit="band"),
    ]

    return ToolResult(
        ok=True,
        tool="get_borrow_readiness",
        data=data.model_dump(),
        facts=facts,
        row_count=1,
    )


class BudgetPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$", description="Optional IST month YYYY-MM")


class BudgetPlanData(BaseModel):
    month: str
    has_plan: bool
    needs_pct: Decimal
    wants_pct: Decimal
    savings_pct: Decimal
    needs_inr: Decimal
    wants_inr: Decimal
    savings_inr: Decimal


async def handle_get_budget_plan(ctx: ToolContext, args: BudgetPlanInput) -> ToolResult:
    target_month = args.month or get_ist_month()
    query = select(BudgetPlan).where(
        BudgetPlan.user_id == ctx.user_id,
        BudgetPlan.month == target_month,
        BudgetPlan.is_current.is_(True),
    )
    res = await _execute(ctx.session, query)
    plan: BudgetPlan | None = res.scalar_one_or_none()

    if plan is None:
        return ToolResult(
            ok=True,
            tool="get_budget_plan",
            data=BudgetPlanData(
                month=target_month,
                has_plan=False,
                needs_pct=Decimal("50.00"),
                wants_pct=Decimal("30.00"),
                savings_pct=Decimal("20.00"),
                needs_inr=Decimal("0.00"),
                wants_inr=Decimal("0.00"),
                savings_inr=Decimal("0.00"),
            ).model_dump(),
            facts=[
                Fact(
                    id="budget_plan_status",
                    label="Budget Plan Status",
                    value="not_configured",
                    unit="status",
                    period=target_month,
                )
            ],
        )

    needs_inr = paise_to_rupees(plan.needs_paise)
    wants_inr = paise_to_rupees(plan.wants_paise)
    savings_inr = paise_to_rupees(plan.savings_paise)
    return ToolResult(
        ok=True,
        tool="get_budget_plan",
        data=BudgetPlanData(
            month=target_month,
            has_plan=True,
            needs_pct=plan.needs_pct,
            wants_pct=plan.wants_pct,
            savings_pct=plan.savings_pct,
            needs_inr=needs_inr,
            wants_inr=wants_inr,
            savings_inr=savings_inr,
        ).model_dump(),
        facts=[
            Fact(id="budget_needs_inr", label="Planned Needs", value=str(needs_inr), unit="INR", period=target_month),
            Fact(id="budget_wants_inr", label="Planned Wants", value=str(wants_inr), unit="INR", period=target_month),
            Fact(
                id="budget_savings_inr",
                label="Planned Savings",
                value=str(savings_inr),
                unit="INR",
                period=target_month,
            ),
        ],
    )


class UpcomingBillsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days_ahead: int = Field(default=7, ge=1, le=30, description="Lookahead window in days")


class UpcomingBillItem(BaseModel):
    name: str
    category: str
    due_date: str
    expected_amount: Decimal
    status: str


class UpcomingBillsData(BaseModel):
    due_soon_count: int
    overdue_count: int
    total_due_inr: Decimal
    bills: list[UpcomingBillItem]


async def handle_get_upcoming_bills(ctx: ToolContext, args: UpcomingBillsInput) -> ToolResult:
    from datetime import timedelta

    today = get_ist_today()
    horizon = today + timedelta(days=args.days_ahead)
    query = (
        select(RecurringOccurrence, RecurringCommitment)
        .join(RecurringCommitment, RecurringOccurrence.commitment_id == RecurringCommitment.id)
        .where(
            RecurringOccurrence.user_id == ctx.user_id,
            RecurringCommitment.is_active.is_(True),
            RecurringOccurrence.status.in_(["upcoming", "overdue", "missed"]),
            RecurringOccurrence.due_date <= horizon,
        )
        .order_by(RecurringOccurrence.due_date.asc())
    )
    res = await _execute(ctx.session, query)
    rows = res.all()

    bills: list[UpcomingBillItem] = []
    due_soon_count = 0
    overdue_count = 0
    total_due = Decimal("0.00")

    for occ, comm in rows:
        is_overdue = occ.due_date < today or occ.status in ("overdue", "missed")
        if is_overdue:
            overdue_count += 1
        else:
            due_soon_count += 1
        amt = quantize_currency(occ.expected_amount)
        total_due += amt
        bills.append(
            UpcomingBillItem(
                name=comm.name,
                category=comm.category,
                due_date=occ.due_date.isoformat(),
                expected_amount=amt,
                status="overdue" if is_overdue else "upcoming",
            )
        )

    return ToolResult(
        ok=True,
        tool="get_upcoming_bills",
        data=UpcomingBillsData(
            due_soon_count=due_soon_count,
            overdue_count=overdue_count,
            total_due_inr=quantize_currency(total_due),
            bills=bills,
        ).model_dump(),
        facts=[
            Fact(id="upcoming_bills_count", label="Upcoming Bills", value=str(due_soon_count), unit="count"),
            Fact(id="overdue_bills_count", label="Overdue Bills", value=str(overdue_count), unit="count"),
            Fact(id="total_due_inr", label="Total Bills Due", value=str(quantize_currency(total_due)), unit="INR"),
        ],
    )


class HealthScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$", description="IST month YYYY-MM")


class HealthScoreToolData(BaseModel):
    formula_version: str
    month: str
    overall_score: int | None
    band: str
    available_components: int
    total_components: int
    best_next_action: str | None
    components: list[dict[str, Any]]


async def handle_get_health_score(ctx: ToolContext, args: HealthScoreInput) -> ToolResult:
    from app.models.user import User
    from app.services.health_score_service import compute_health_score

    u_res = await _execute(ctx.session, select(User).where(User.id == ctx.user_id))
    user = u_res.scalar_one_or_none()
    if user is None:
        return ToolResult(ok=False, tool="get_health_score", data={"error": "User not found"})

    res = await compute_health_score(ctx.session, user, month=args.month, record_snapshot=False)
    best_title = res.best_next_action.title if res.best_next_action else None
    facts = [
        Fact(id="health_formula_version", label="Formula Version", value=res.formula_version, unit="version"),
        Fact(id="health_band", label="Health Band", value=res.band, unit="band", period=res.month),
        Fact(
            id="health_available_components",
            label="Available Components",
            value=str(res.available_components),
            unit="count",
        ),
    ]
    if res.overall_score is not None:
        facts.append(
            Fact(
                id="health_score",
                label="Float Health Score",
                value=str(res.overall_score),
                unit="score_0_100",
                period=res.month,
            )
        )
    if best_title:
        facts.append(Fact(id="best_next_action", label="Best Next Action", value=best_title, unit="step"))

    return ToolResult(
        ok=True,
        tool="get_health_score",
        data=HealthScoreToolData(
            formula_version=res.formula_version,
            month=res.month,
            overall_score=res.overall_score,
            band=res.band,
            available_components=res.available_components,
            total_components=res.total_components,
            best_next_action=best_title,
            components=[c.model_dump() for c in res.components],
        ).model_dump(),
        facts=facts,
    )


# ============================================================================
# Tool Specifications and Registration
# ============================================================================


def register_financial_tools() -> None:
    """Register all core financial analytical tools into default_registry."""
    tools = [
        Tool(
            name="get_spending_summary",
            description=(
                "Calculate total debits (expenses), total credits (income), net cash flow, "
                "and transaction count for a specified date range. Excludes internal account transfers."
            ),
            input_model=SpendingSummaryInput,
            output_model=SpendingSummaryData,
            handler=handle_spending_summary,
        ),
        Tool(
            name="get_category_breakdown",
            description=(
                "Provide detailed category breakdown for debits (spending) across a date range, "
                "returning top N categories by spending amount, percentage share, and an 'Other' bucket."
            ),
            input_model=CategoryBreakdownInput,
            output_model=CategoryBreakdownData,
            handler=handle_category_breakdown,
        ),
        Tool(
            name="compare_periods",
            description=(
                "Compare financial spending, income, and net cash flow across two distinct date periods "
                "(Period A as baseline, Period B as comparison). Computes absolute differences and percentage changes."
            ),
            input_model=ComparePeriodsInput,
            output_model=ComparePeriodsData,
            handler=handle_compare_periods,
        ),
        Tool(
            name="get_cash_flow",
            description=(
                "Compute aggregated cash inflow, outflow, and net balance over time buckets "
                "(daily, weekly, or monthly) for trend analysis."
            ),
            input_model=CashFlowInput,
            output_model=CashFlowData,
            handler=handle_cash_flow,
        ),
        Tool(
            name="list_recurring_payments",
            description=(
                "List all declared or confirmed recurring commitments (subscriptions, bills, EMIs) "
                "along with their frequency, expected amount, due day, and total monthly committed outflow."
            ),
            input_model=ListRecurringPaymentsInput,
            output_model=ListRecurringPaymentsData,
            handler=handle_list_recurring,
        ),
        Tool(
            name="get_borrow_readiness",
            description=(
                "Retrieve indicative borrow readiness assessment (band and key risk/positive factors). "
                "Never returns an invented credit score. If no assessment is available, returns insufficient_data."
            ),
            input_model=BorrowReadinessInput,
            output_model=BorrowReadinessData,
            handler=handle_borrow_readiness,
        ),
        Tool(
            name="get_budget_plan",
            description=(
                "Retrieve the user's monthly INR budget plan (needs/wants/savings percentages and planned amounts) "
                "for an IST calendar month."
            ),
            input_model=BudgetPlanInput,
            output_model=BudgetPlanData,
            handler=handle_get_budget_plan,
        ),
        Tool(
            name="get_recurring_payments",
            description=(
                "List declared or confirmed recurring commitments (rent, EMIs, SIPs, subscriptions, bills) "
                "with frequency, expected amount, and due day."
            ),
            input_model=ListRecurringPaymentsInput,
            output_model=ListRecurringPaymentsData,
            handler=handle_list_recurring,
        ),
        Tool(
            name="get_upcoming_bills",
            description=(
                "List upcoming and overdue recurring bill reminders within a lookahead window (in IST)."
            ),
            input_model=UpcomingBillsInput,
            output_model=UpcomingBillsData,
            handler=handle_get_upcoming_bills,
        ),
        Tool(
            name="get_health_score",
            description=(
                "Compute the deterministic, versioned Float Health Score (0-100), 6 component statuses "
                "(savings rate, emergency fund months, DTI, budget adherence, subscriptions share, insurance flag), "
                "and ordered Float Path next steps."
            ),
            input_model=HealthScoreInput,
            output_model=HealthScoreToolData,
            handler=handle_get_health_score,
        ),
    ]

    for tool in tools:
        try:
            default_registry.register(tool)
        except ValueError:
            # Already registered
            pass
