import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_consent
from app.core.errors import BadRequestException, ConflictException, NotFoundException, PayloadTooLargeException
from app.models.budget import DEFAULT_CATEGORY_MAPPINGS, BudgetPlan
from app.models.enums import (
    AccountStatus,
    AccountType,
    AuditActor,
    ConsentType,
    ImportStatus,
    TransactionSource,
    TransactionType,
)
from app.models.goals import EmergencyFundConfig, Goal
from app.models.plan import Account, Transaction, TransactionImport
from app.models.protect import AuditTrail
from app.models.subscriptions_networth import NetWorthItem, NetWorthSnapshot, SubscriptionLeakDecision
from app.models.user import User
from app.services.budget_service import (
    BUDGET_PRESETS,
    MAX_INCOME_PAISE,
    allocate_budget_paise,
    compute_irregular_avg_paise,
    compute_plan_vs_actual,
    get_ist_month,
)
from app.services.calculators_service import (
    InsuranceGapResponse,
    SipProjectionResponse,
    TaxComparisonResponse,
    calculate_insurance_gap,
    calculate_sip_projection,
    compare_tax_regimes,
)
from app.services.cash_flow import compute_financial_insights, compute_monthly_cash_flow
from app.services.goals_service import (
    EmergencyFundResponse,
    GoalsOverviewResponse,
    compute_emergency_fund_overview,
    compute_goals_overview,
)
from app.services.health_score_service import FORMULA_VERSION, HealthScoreResponse, compute_health_score
from app.services.recurring_service import match_transaction_to_occurrence
from app.services.statement_parser import (
    StatementParseError,
    parse_csv_statement,
    parse_sms_statement,
)
from app.services.subscriptions_networth_service import (
    NetWorthOverviewResponse,
    SubscriptionLeaksResponse,
    compute_net_worth_overview,
    compute_subscription_leaks,
)

router = APIRouter(prefix="/plan", tags=["Plan — Personal Finance Management"])


class CreateAccountRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Primary HDFC Savings"})
    account_type: str = Field("savings", json_schema_extra={"example": "savings"})  # savings, checking, credit_card
    institution_name: str = Field("HDFC Bank", json_schema_extra={"example": "HDFC Bank"})
    account_number_mask: str = Field("****1234", json_schema_extra={"example": "****1234"})
    currency: Literal["INR"] = Field("INR", json_schema_extra={"example": "INR"})
    initial_balance: float = Field(0.0, json_schema_extra={"example": 50000.0})


class AccountResponse(BaseModel):
    id: str
    user_id: str
    name: str
    account_type: str
    institution_name: str
    account_number_mask: str
    currency: str
    current_balance: float
    created_at: str


class UploadStatementRequest(BaseModel):
    account_id: str
    format: str = Field("csv", json_schema_extra={"example": "csv"})  # csv or sms
    content: str = Field(..., description="Raw text of the CSV or bank SMS alert")


class StatementUploadSummary(BaseModel):
    account_id: str
    total_parsed: int
    imported_count: int
    duplicates_skipped: int
    sample_imported: list[dict[str, Any]]


def _parse_account_type(type_str: str) -> AccountType:
    try:
        return AccountType(type_str.lower().strip())
    except ValueError as err:
        valid_types = [e.value for e in AccountType]
        raise BadRequestException(f"Invalid account_type '{type_str}'. Allowed values are: {valid_types}") from err


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(
    req: CreateAccountRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Create a new financial account (savings, checking, credit card). Requires terms consent."""
    account = Account(
        user_id=current_user.id,
        name=req.name,
        account_type=_parse_account_type(req.account_type),
        status=AccountStatus.ACTIVE,
        institution_name=req.institution_name,
        account_number_mask=req.account_number_mask,
        currency=req.currency,
        reported_balance=Decimal(str(req.initial_balance)),
        reported_balance_at=datetime.now(UTC),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return AccountResponse(
        id=str(account.id),
        user_id=str(account.user_id),
        name=account.name,
        account_type=account.account_type.value,
        institution_name=account.institution_name,
        account_number_mask=account.account_number_mask,
        currency=account.currency,
        current_balance=float(account.reported_balance),
        created_at=account.created_at.isoformat(),
    )


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[AccountResponse]:
    """Retrieve all accounts belonging to the authenticated user."""
    stmt = select(Account).where(Account.user_id == current_user.id).order_by(Account.created_at.desc())
    result = await db.execute(stmt)
    accounts = result.scalars().all()

    return [
        AccountResponse(
            id=str(acc.id),
            user_id=str(acc.user_id),
            name=acc.name,
            account_type=acc.account_type.value,
            institution_name=acc.institution_name,
            account_number_mask=acc.account_number_mask,
            currency=acc.currency,
            current_balance=float(acc.reported_balance),
            created_at=acc.created_at.isoformat(),
        )
        for acc in accounts
    ]


@router.post(
    "/upload-statement",
    response_model=StatementUploadSummary,
    responses={413: {"description": "Statement content exceeds maximum allowed size of 10 MB."}},
)
async def upload_statement(
    req: UploadStatementRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> StatementUploadSummary:
    """Upload a bank statement (CSV or SMS text) with automatic deduplication, sanitization, and categorization."""
    try:
        acc_uuid = uuid.UUID(req.account_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Specified account does not exist or does not belong to you.") from err

    stmt = select(Account).where(Account.id == acc_uuid, Account.user_id == current_user.id)
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        raise NotFoundException("Specified account does not exist or does not belong to you.")

    if len(req.content.encode("utf-8")) > 10 * 1024 * 1024:
        raise PayloadTooLargeException("Statement content exceeds maximum allowed size of 10 MB.")

    is_sms = req.format.lower() == "sms"
    try:
        if is_sms:
            parsed_single = parse_sms_statement(req.content, str(account.id))
            parsed_txs = [parsed_single] if parsed_single else []
        else:
            parsed_txs = parse_csv_statement(req.content, str(account.id))
    except StatementParseError as err:
        raise BadRequestException(str(err)) from err

    if not parsed_txs:
        raise BadRequestException("Could not extract any valid transactions from the provided content.")

    # Create transaction import record
    tx_import = TransactionImport(
        user_id=current_user.id,
        account_id=account.id,
        source=TransactionSource.SMS if is_sms else TransactionSource.CSV_UPLOAD,
        status=ImportStatus.PROCESSING,
        total_parsed=len(parsed_txs),
        imported_count=0,
        duplicates_skipped=0,
        error_count=0,
        started_at=datetime.now(UTC),
    )
    db.add(tx_import)
    await db.flush()

    # Query existing fingerprints for this user to prevent duplicates
    fingerprints = [t["fingerprint"] for t in parsed_txs]
    existing_fp_stmt = select(Transaction.normalized_fingerprint).where(
        Transaction.user_id == current_user.id,
        Transaction.normalized_fingerprint.in_(fingerprints),
    )
    existing_fp_res = await db.execute(existing_fp_stmt)
    seen_fps = set(existing_fp_res.scalars().all())

    imported: list[dict[str, Any]] = []
    skipped_count = 0

    for tx in parsed_txs:
        fp = tx["fingerprint"]
        if fp in seen_fps:
            skipped_count += 1
            continue

        seen_fps.add(fp)
        t_type = TransactionType.CREDIT if tx["transaction_type"].lower() == "credit" else TransactionType.DEBIT
        amt_decimal = Decimal(str(tx["amount"]))

        new_tx_id = uuid.uuid4()
        new_tx = Transaction(
            id=new_tx_id,
            user_id=current_user.id,
            account_id=account.id,
            import_id=tx_import.id,
            transaction_date=tx["date"],
            amount=amt_decimal,
            transaction_type=t_type,
            category=tx.get("category", "Other"),
            description=tx.get("description", ""),
            description_cleaned=tx.get("description_cleaned", ""),
            merchant=tx.get("merchant"),
            normalized_merchant=tx.get("merchant", "").lower() if tx.get("merchant") else None,
            normalized_fingerprint=fp,
            source=TransactionSource.SMS if is_sms else TransactionSource.CSV_UPLOAD,
        )
        db.add(new_tx)
        await db.flush()

        # Update balance
        if t_type == TransactionType.CREDIT:
            account.reported_balance += amt_decimal
        else:
            account.reported_balance -= amt_decimal

        if t_type == TransactionType.DEBIT:
            await match_transaction_to_occurrence(db, current_user.id, new_tx)

        tx_record = {
            "id": str(new_tx.id),
            "account_id": str(account.id),
            "user_id": str(current_user.id),
            "date": tx["date"].isoformat() if isinstance(tx["date"], datetime) else str(tx["date"]),
            "amount": float(amt_decimal),
            "transaction_type": t_type.value,
            "category": new_tx.category,
            "description": new_tx.description,
            "description_cleaned": new_tx.description_cleaned,
            "merchant": new_tx.merchant,
        }
        imported.append(tx_record)

    tx_import.imported_count = len(imported)
    tx_import.duplicates_skipped = skipped_count
    tx_import.status = ImportStatus.COMPLETED
    tx_import.completed_at = datetime.now(UTC)

    await db.commit()

    return StatementUploadSummary(
        account_id=str(account.id),
        total_parsed=len(parsed_txs),
        imported_count=len(imported),
        duplicates_skipped=skipped_count,
        sample_imported=imported[:5],
    )


@router.get("/transactions")
async def list_transactions(
    account_id: str | None = None,
    category: str | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List transactions with optional filtering by account and category."""
    query = (
        select(Transaction).where(Transaction.user_id == current_user.id).order_by(Transaction.transaction_date.desc())
    )

    if account_id:
        try:
            acc_uuid = uuid.UUID(account_id)
            query = query.where(Transaction.account_id == acc_uuid)
        except (ValueError, TypeError):
            return []

    if category:
        query = query.where(Transaction.category.ilike(category))

    result = await db.execute(query)
    txs = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "account_id": str(t.account_id),
            "user_id": str(t.user_id),
            "date": t.transaction_date.isoformat(),
            "amount": float(t.amount),
            "transaction_type": t.transaction_type.value,
            "category": t.category,
            "description": t.description,
            "description_cleaned": t.description_cleaned,
            "merchant": t.merchant,
            "is_recurring": t.is_recurring,
        }
        for t in txs
    ]


@router.get("/cash-flow")
async def get_cash_flow(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Calculate monthly cash flow (inflow, outflow, net savings, savings rate)."""
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    result = await db.execute(stmt)
    tx_models = result.scalars().all()

    tx_dicts = [
        {
            "date": t.transaction_date,
            "amount": float(t.amount),
            "transaction_type": t.transaction_type.value,
            "category": t.category,
        }
        for t in tx_models
    ]
    return compute_monthly_cash_flow(tx_dicts)


@router.get("/insights")
async def get_insights(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve personal finance insights: income volatility, balance runway, top spending categories."""
    tx_stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    tx_result = await db.execute(tx_stmt)
    tx_models = tx_result.scalars().all()

    acc_stmt = select(Account).where(Account.user_id == current_user.id)
    acc_result = await db.execute(acc_stmt)
    acc_models = acc_result.scalars().all()

    total_balance = sum(float(a.reported_balance) for a in acc_models)

    tx_dicts = [
        {
            "date": t.transaction_date,
            "amount": float(t.amount),
            "transaction_type": t.transaction_type.value,
            "category": t.category,
        }
        for t in tx_models
    ]
    return compute_financial_insights(tx_dicts, current_balance=total_balance)


class BudgetPlanUpsertRequest(BaseModel):
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    monthly_income_paise: int = Field(..., gt=0, le=MAX_INCOME_PAISE)
    extra_income_paise: int = Field(default=0, ge=0, le=MAX_INCOME_PAISE)
    income_mode: Literal["fixed", "irregular_avg", "irregular_conservative"] = "fixed"
    irregular_months: int = Field(default=3, ge=1, le=12)
    needs_pct: Decimal = Field(default=Decimal("50.00"), ge=Decimal("0"), le=Decimal("100"))
    wants_pct: Decimal = Field(default=Decimal("30.00"), ge=Decimal("0"), le=Decimal("100"))
    savings_pct: Decimal = Field(default=Decimal("20.00"), ge=Decimal("0"), le=Decimal("100"))
    category_mappings: dict[str, Literal["needs", "wants", "savings"]] | None = None
    expected_version: int | None = Field(default=None, ge=0)


class BudgetPlanItemResponse(BaseModel):
    id: str
    month: str
    version: int
    monthly_income_paise: int
    extra_income_paise: int
    total_income_paise: int
    income_mode: str
    irregular_months: int
    needs_pct: float
    wants_pct: float
    savings_pct: float
    needs_paise: int
    wants_paise: int
    savings_paise: int
    category_mappings: dict[str, str]
    updated_at: str


class BudgetPlanOverviewResponse(BaseModel):
    month: str
    plan: BudgetPlanItemResponse | None
    actuals: dict[str, Any]
    irregular_avg_paise: int
    presets: dict[str, dict[str, float]]
    default_category_mappings: dict[str, str]
    educational_disclaimer: str


def _serialize_budget_plan(plan: BudgetPlan) -> BudgetPlanItemResponse:
    return BudgetPlanItemResponse(
        id=str(plan.id),
        month=plan.month,
        version=plan.version,
        monthly_income_paise=plan.monthly_income_paise,
        extra_income_paise=plan.extra_income_paise,
        total_income_paise=plan.monthly_income_paise + plan.extra_income_paise,
        income_mode=plan.income_mode,
        irregular_months=plan.irregular_months,
        needs_pct=float(plan.needs_pct),
        wants_pct=float(plan.wants_pct),
        savings_pct=float(plan.savings_pct),
        needs_paise=plan.needs_paise,
        wants_paise=plan.wants_paise,
        savings_paise=plan.savings_paise,
        category_mappings={str(k): str(v) for k, v in (plan.category_mappings or {}).items()},
        updated_at=plan.updated_at.isoformat(),
    )


@router.get("/budget", response_model=BudgetPlanOverviewResponse)
async def get_budget_plan(
    month: str | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> BudgetPlanOverviewResponse:
    """Get current versioned budget plan for an IST month with deterministic actuals and warnings."""
    target_month = month or get_ist_month()
    stmt = select(BudgetPlan).where(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == target_month,
        BudgetPlan.is_current.is_(True),
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    actuals = await compute_plan_vs_actual(db, current_user.id, target_month, plan)
    irregular_avg = await compute_irregular_avg_paise(db, current_user.id, months=3, as_of_month=target_month)
    presets = {k: {bk: float(bv) for bk, bv in v.items()} for k, v in BUDGET_PRESETS.items()}

    return BudgetPlanOverviewResponse(
        month=target_month,
        plan=_serialize_budget_plan(plan) if plan else None,
        actuals=actuals,
        irregular_avg_paise=irregular_avg,
        presets=presets,
        default_category_mappings=dict(DEFAULT_CATEGORY_MAPPINGS),
        educational_disclaimer="For educational and personal planning only; not investment advice.",
    )


@router.get("/budget/history", response_model=list[BudgetPlanItemResponse])
async def get_budget_plan_history(
    month: str | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetPlanItemResponse]:
    """List version history of budget plans for the given IST month."""
    target_month = month or get_ist_month()
    stmt = (
        select(BudgetPlan)
        .where(BudgetPlan.user_id == current_user.id, BudgetPlan.month == target_month)
        .order_by(BudgetPlan.version.desc())
    )
    res = await db.execute(stmt)
    return [_serialize_budget_plan(p) for p in res.scalars().all()]


@router.put("/budget", response_model=BudgetPlanItemResponse)
async def upsert_budget_plan(
    req: BudgetPlanUpsertRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> BudgetPlanItemResponse:
    """Create or update a monthly budget plan with optimistic concurrency and largest-remainder rounding."""
    target_month = req.month or get_ist_month()
    total_income_paise = req.monthly_income_paise + req.extra_income_paise
    try:
        needs_paise, wants_paise, savings_paise = allocate_budget_paise(
            total_income_paise,
            req.needs_pct,
            req.wants_pct,
            req.savings_pct,
        )
    except ValueError as err:
        raise BadRequestException(str(err)) from err

    stmt = select(BudgetPlan).where(
        BudgetPlan.user_id == current_user.id,
        BudgetPlan.month == target_month,
        BudgetPlan.is_current.is_(True),
    )
    res = await db.execute(stmt)
    current = res.scalar_one_or_none()

    if current is not None:
        if req.expected_version is not None and req.expected_version != current.version:
            raise ConflictException(
                "Budget plan was updated in another tab or session. Please reload and try again."
            )
        current.is_current = False
        next_version = current.version + 1
    else:
        if req.expected_version not in (None, 0):
            raise ConflictException("Budget plan version mismatch. Please reload and try again.")
        next_version = 1

    merged_mappings = dict(DEFAULT_CATEGORY_MAPPINGS)
    if req.category_mappings:
        merged_mappings.update(req.category_mappings)

    new_plan = BudgetPlan(
        user_id=current_user.id,
        month=target_month,
        version=next_version,
        is_current=True,
        monthly_income_paise=req.monthly_income_paise,
        extra_income_paise=req.extra_income_paise,
        income_mode=req.income_mode,
        irregular_months=req.irregular_months,
        needs_pct=req.needs_pct.quantize(Decimal("0.01")),
        wants_pct=req.wants_pct.quantize(Decimal("0.01")),
        savings_pct=req.savings_pct.quantize(Decimal("0.01")),
        needs_paise=needs_paise,
        wants_paise=wants_paise,
        savings_paise=savings_paise,
        category_mappings=merged_mappings,
    )
    db.add(new_plan)
    await db.flush()
    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="budget_plan_updated",
            resource_type="budget_plan",
            resource_id=str(new_plan.id),
            metadata_json={"month": target_month, "version": next_version, "income_mode": req.income_mode},
        )
    )
    await db.commit()
    await db.refresh(new_plan)
    return _serialize_budget_plan(new_plan)


class HealthInsuranceFlagRequest(BaseModel):
    has_essential_insurance: bool | None = Field(
        default=None,
        description="Self-reported essential health/term insurance status (true, false, or null if unknown).",
    )


@router.get("/health-score", response_model=HealthScoreResponse)
async def get_health_score_endpoint(
    month: str | None = None,
    formula_version: str | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> HealthScoreResponse:
    """Compute deterministic, explainable, versioned Float Health Score and Float Path."""
    res = await compute_health_score(
        db,
        current_user,
        month=month,
        formula_version=formula_version or FORMULA_VERSION,
        record_snapshot=True,
    )
    await db.commit()
    return res


@router.put("/health-score/insurance", response_model=HealthScoreResponse)
async def update_health_insurance_flag(
    req: HealthInsuranceFlagRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> HealthScoreResponse:
    """Update user-entered essential insurance flag and recompute Float Health Score."""
    prefs = dict(current_user.notification_preferences or {})
    if req.has_essential_insurance is None:
        prefs.pop("has_essential_insurance", None)
    else:
        prefs["has_essential_insurance"] = bool(req.has_essential_insurance)
    current_user.notification_preferences = prefs

    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="health_insurance_flag_updated",
            resource_type="health_score",
            resource_id=str(current_user.id),
            metadata_json={"has_essential_insurance": req.has_essential_insurance},
        )
    )
    await db.flush()
    res = await compute_health_score(db, current_user, record_snapshot=True)
    await db.commit()
    return res


class CreateGoalRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    target_amount_paise: int = Field(..., gt=0)
    saved_paise: int = Field(0, ge=0)
    target_date: date
    priority: int = Field(1, ge=1)


class UpdateGoalRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount_paise: int | None = Field(default=None, gt=0)
    saved_paise: int | None = Field(default=None, ge=0)
    target_date: date | None = None
    priority: int | None = Field(default=None, ge=1)
    expected_version: int | None = None


class UpdateEmergencyFundRequest(BaseModel):
    target_months: int = Field(..., ge=0, le=36)
    saved_paise: int = Field(0, ge=0)
    expected_version: int | None = None


@router.get("/goals", response_model=GoalsOverviewResponse)
async def get_goals_endpoint(
    month: str | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> GoalsOverviewResponse:
    return await compute_goals_overview(db, current_user.id, month=month)


@router.post("/goals", response_model=GoalsOverviewResponse, status_code=201)
async def create_goal_endpoint(
    req: CreateGoalRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> GoalsOverviewResponse:
    goal = Goal(
        user_id=current_user.id,
        name=req.name.strip(),
        target_amount_paise=req.target_amount_paise,
        saved_paise=req.saved_paise,
        target_date=req.target_date,
        priority=req.priority,
        version=1,
    )
    db.add(goal)
    await db.flush()
    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="goal_created",
            resource_type="goal",
            resource_id=str(goal.id),
            metadata_json={"priority": goal.priority},
        )
    )
    await db.commit()
    return await compute_goals_overview(db, current_user.id)


@router.put("/goals/{goal_id}", response_model=GoalsOverviewResponse)
async def update_goal_endpoint(
    goal_id: uuid.UUID,
    req: UpdateGoalRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> GoalsOverviewResponse:
    res = await db.execute(select(Goal).where(Goal.id == goal_id, Goal.user_id == current_user.id))
    goal = res.scalar_one_or_none()
    if goal is None:
        raise NotFoundException("Goal not found.")
    if req.expected_version is not None and req.expected_version != goal.version:
        raise ConflictException("Goal was changed elsewhere. Latest version reloaded.")

    if req.name is not None:
        goal.name = req.name.strip()
    if req.target_amount_paise is not None:
        goal.target_amount_paise = req.target_amount_paise
    if req.saved_paise is not None:
        goal.saved_paise = req.saved_paise
    if req.target_date is not None:
        goal.target_date = req.target_date
    if req.priority is not None:
        goal.priority = req.priority
    goal.version += 1

    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="goal_updated",
            resource_type="goal",
            resource_id=str(goal.id),
            metadata_json={"version": goal.version, "priority": goal.priority},
        )
    )
    await db.commit()
    return await compute_goals_overview(db, current_user.id)


@router.delete("/goals/{goal_id}", response_model=GoalsOverviewResponse)
async def delete_goal_endpoint(
    goal_id: uuid.UUID,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> GoalsOverviewResponse:
    res = await db.execute(select(Goal).where(Goal.id == goal_id, Goal.user_id == current_user.id))
    goal = res.scalar_one_or_none()
    if goal is None:
        raise NotFoundException("Goal not found.")
    await db.delete(goal)
    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="goal_deleted",
            resource_type="goal",
            resource_id=str(goal_id),
            metadata_json={},
        )
    )
    await db.commit()
    return await compute_goals_overview(db, current_user.id)


@router.get("/emergency-fund", response_model=EmergencyFundResponse)
async def get_emergency_fund_endpoint(
    month: str | None = None,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> EmergencyFundResponse:
    return await compute_emergency_fund_overview(db, current_user.id, month=month)


@router.put("/emergency-fund", response_model=EmergencyFundResponse)
async def update_emergency_fund_endpoint(
    req: UpdateEmergencyFundRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> EmergencyFundResponse:
    res = await db.execute(select(EmergencyFundConfig).where(EmergencyFundConfig.user_id == current_user.id))
    cfg = res.scalar_one_or_none()
    if cfg is not None:
        if req.expected_version is not None and req.expected_version != cfg.version:
            raise ConflictException("Emergency fund config was changed elsewhere. Latest version reloaded.")
        cfg.target_months = req.target_months
        cfg.saved_paise = req.saved_paise
        cfg.version += 1
        cfg_id = cfg.id
        new_ver = cfg.version
    else:
        if req.expected_version not in (None, 0):
            raise ConflictException("Emergency fund config was changed elsewhere. Latest version reloaded.")
        cfg = EmergencyFundConfig(
            user_id=current_user.id,
            target_months=req.target_months,
            saved_paise=req.saved_paise,
            version=1,
        )
        db.add(cfg)
        await db.flush()
        cfg_id = cfg.id
        new_ver = 1

    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="emergency_fund_updated",
            resource_type="emergency_fund",
            resource_id=str(cfg_id),
            metadata_json={"target_months": req.target_months, "version": new_ver},
        )
    )
    await db.commit()
    return await compute_emergency_fund_overview(db, current_user.id)


class LeakDecisionRequest(BaseModel):
    decision: Literal["keep", "cancel"]


class CreateNetWorthItemRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    item_type: Literal["asset", "liability"]
    category: str = Field("other", min_length=1, max_length=64)
    amount_paise: int = Field(..., ge=0)
    valued_at: datetime | None = None


class UpdateNetWorthItemRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    amount_paise: int | None = Field(default=None, ge=0)
    valued_at: datetime | None = None
    expected_version: int | None = None


class CreateSnapshotRequest(BaseModel):
    snapshot_date: date | None = None


@router.get("/subscriptions/leaks", response_model=SubscriptionLeaksResponse)
async def get_subscription_leaks_endpoint(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionLeaksResponse:
    return await compute_subscription_leaks(db, current_user.id)


@router.put("/subscriptions/leaks/{leak_key}", response_model=SubscriptionLeaksResponse)
async def set_subscription_leak_decision(
    leak_key: str,
    req: LeakDecisionRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionLeaksResponse:
    res = await db.execute(
        select(SubscriptionLeakDecision).where(
            SubscriptionLeakDecision.user_id == current_user.id,
            SubscriptionLeakDecision.leak_key == leak_key,
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        existing.decision = req.decision
    else:
        db.add(
            SubscriptionLeakDecision(
                user_id=current_user.id,
                leak_key=leak_key,
                decision=req.decision,
            )
        )
    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="subscription_leak_decision",
            resource_type="subscription_leak",
            resource_id=leak_key,
            metadata_json={"decision": req.decision},
        )
    )
    await db.commit()
    return await compute_subscription_leaks(db, current_user.id)


@router.get("/net-worth", response_model=NetWorthOverviewResponse)
async def get_net_worth_endpoint(
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> NetWorthOverviewResponse:
    return await compute_net_worth_overview(db, current_user.id)


@router.post("/net-worth/items", response_model=NetWorthOverviewResponse, status_code=201)
async def create_net_worth_item_endpoint(
    req: CreateNetWorthItemRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> NetWorthOverviewResponse:
    item = NetWorthItem(
        user_id=current_user.id,
        name=req.name.strip(),
        item_type=req.item_type,
        category=req.category.strip(),
        amount_paise=req.amount_paise,
        valued_at=req.valued_at or datetime.now(UTC),
        version=1,
    )
    db.add(item)
    await db.flush()
    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="net_worth_item_created",
            resource_type="net_worth_item",
            resource_id=str(item.id),
            metadata_json={"item_type": item.item_type, "category": item.category},
        )
    )
    await db.commit()
    return await compute_net_worth_overview(db, current_user.id)


@router.put("/net-worth/items/{item_id}", response_model=NetWorthOverviewResponse)
async def update_net_worth_item_endpoint(
    item_id: uuid.UUID,
    req: UpdateNetWorthItemRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> NetWorthOverviewResponse:
    res = await db.execute(
        select(NetWorthItem).where(NetWorthItem.id == item_id, NetWorthItem.user_id == current_user.id)
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise NotFoundException("Net worth item not found.")
    if req.expected_version is not None and req.expected_version != item.version:
        raise ConflictException("Net worth item was changed elsewhere. Latest version reloaded.")

    if req.name is not None:
        item.name = req.name.strip()
    if req.category is not None:
        item.category = req.category.strip()
    if req.amount_paise is not None:
        item.amount_paise = req.amount_paise
        item.valued_at = req.valued_at or datetime.now(UTC)
    elif req.valued_at is not None:
        item.valued_at = req.valued_at
    item.version += 1

    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="net_worth_item_updated",
            resource_type="net_worth_item",
            resource_id=str(item.id),
            metadata_json={"version": item.version},
        )
    )
    await db.commit()
    return await compute_net_worth_overview(db, current_user.id)


@router.delete("/net-worth/items/{item_id}", response_model=NetWorthOverviewResponse)
async def delete_net_worth_item_endpoint(
    item_id: uuid.UUID,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> NetWorthOverviewResponse:
    res = await db.execute(
        select(NetWorthItem).where(NetWorthItem.id == item_id, NetWorthItem.user_id == current_user.id)
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise NotFoundException("Net worth item not found.")
    await db.delete(item)
    db.add(
        AuditTrail(
            user_id=current_user.id,
            actor=AuditActor.USER,
            action="net_worth_item_deleted",
            resource_type="net_worth_item",
            resource_id=str(item_id),
            metadata_json={},
        )
    )
    await db.commit()
    return await compute_net_worth_overview(db, current_user.id)


@router.post("/net-worth/snapshots", response_model=NetWorthOverviewResponse, status_code=201)
async def create_net_worth_snapshot_endpoint(
    req: CreateSnapshotRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> NetWorthOverviewResponse:
    ov = await compute_net_worth_overview(db, current_user.id)
    snap_date = req.snapshot_date or datetime.now(UTC).date()
    snap = NetWorthSnapshot(
        user_id=current_user.id,
        snapshot_date=snap_date,
        total_assets_paise=ov.total_assets_paise,
        total_liabilities_paise=ov.total_liabilities_paise,
        net_worth_paise=ov.net_worth_paise,
    )
    db.add(snap)
    await db.commit()
    return await compute_net_worth_overview(db, current_user.id)


class SipCalculatorRequest(BaseModel):
    mode: Literal["forward", "reverse"] = "forward"
    monthly_sip_paise: int = Field(0, ge=0, le=10_000_000_00)
    target_amount_paise: int | None = Field(default=None, gt=0, le=1_000_000_000_00)
    lumpsum_paise: int = Field(0, ge=0, le=100_000_000_00)
    years: int = Field(..., ge=1, le=50)
    expected_return_pct: Decimal = Field(Decimal("10"), ge=Decimal("0"), le=Decimal("30"))
    step_up_type: Literal["none", "percent", "amount"] = "none"
    step_up_interval_months: Literal[1, 2, 3, 6, 12] = 12
    step_up_percent: Decimal = Field(Decimal("0"), ge=Decimal("0"), le=Decimal("100"))
    step_up_amount_paise: int = Field(0, ge=0, le=10_000_000_00)
    adjust_for_inflation: bool = True
    inflation_pct: Decimal = Field(Decimal("6"), ge=Decimal("0"), le=Decimal("20"))
    max_income_share_pct: Decimal = Field(Decimal("50"), gt=Decimal("0"), le=Decimal("100"))


class InsuranceGapRequest(BaseModel):
    annual_income_paise: int = Field(..., ge=0, le=100_000_000_00)
    dependants: int = Field(0, ge=0, le=20)
    existing_life_cover_paise: int = Field(0, ge=0, le=1_000_000_000_00)
    existing_health_cover_paise: int = Field(0, ge=0, le=100_000_000_00)
    liabilities_paise: int = Field(0, ge=0, le=100_000_000_00)


class TaxCompareRequest(BaseModel):
    gross_income_paise: int = Field(..., ge=0, le=100_000_000_00)
    is_salaried: bool = True
    deduction_80c_paise: int = Field(0, ge=0, le=15_000_000)
    deduction_80d_paise: int = Field(0, ge=0, le=10_000_000)
    other_deductions_paise: int = Field(0, ge=0, le=50_000_000_00)


@router.post("/calculators/sip", response_model=SipProjectionResponse)
async def sip_calculator_endpoint(
    req: SipCalculatorRequest,
    current_user: User = Depends(require_consent(ConsentType.TERMS)),
    db: AsyncSession = Depends(get_db),
) -> SipProjectionResponse:
    if req.mode == "reverse" and (req.target_amount_paise is None or req.target_amount_paise <= 0):
        raise BadRequestException("Target amount must be greater than 0 for reverse SIP mode.")
    budget_res = await db.execute(
        select(BudgetPlan)
        .where(BudgetPlan.user_id == current_user.id, BudgetPlan.is_current.is_(True))
        .order_by(BudgetPlan.updated_at.desc())
        .limit(1)
    )
    budget = budget_res.scalar_one_or_none()
    monthly_income_paise = (budget.monthly_income_paise + budget.extra_income_paise) if budget is not None else None
    return calculate_sip_projection(
        monthly_sip_paise=req.monthly_sip_paise,
        lumpsum_paise=req.lumpsum_paise,
        years=req.years,
        expected_return_pct=req.expected_return_pct,
        adjust_for_inflation=req.adjust_for_inflation,
        inflation_pct=req.inflation_pct,
        mode=req.mode,
        target_amount_paise=req.target_amount_paise,
        step_up_type=req.step_up_type,
        step_up_interval_months=req.step_up_interval_months,
        step_up_percent=req.step_up_percent,
        step_up_amount_paise=req.step_up_amount_paise,
        monthly_income_paise=monthly_income_paise,
        max_income_share_pct=req.max_income_share_pct,
    )


@router.post("/calculators/insurance-gap", response_model=InsuranceGapResponse)
async def insurance_gap_endpoint(
    req: InsuranceGapRequest,
    _current_user: User = Depends(require_consent(ConsentType.TERMS)),
) -> InsuranceGapResponse:
    return calculate_insurance_gap(
        annual_income_paise=req.annual_income_paise,
        dependants=req.dependants,
        existing_life_cover_paise=req.existing_life_cover_paise,
        existing_health_cover_paise=req.existing_health_cover_paise,
        liabilities_paise=req.liabilities_paise,
    )


@router.post("/calculators/tax-compare", response_model=TaxComparisonResponse)
async def tax_compare_endpoint(
    req: TaxCompareRequest,
    _current_user: User = Depends(require_consent(ConsentType.TERMS)),
) -> TaxComparisonResponse:
    return compare_tax_regimes(
        gross_income_paise=req.gross_income_paise,
        is_salaried=req.is_salaried,
        deduction_80c_paise=req.deduction_80c_paise,
        deduction_80d_paise=req.deduction_80d_paise,
        other_deductions_paise=req.other_deductions_paise,
    )
