import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.tools.base import (
    Tool,
    ToolContext,
    ToolResult,
    calculate_percentage_change,
    quantize_currency,
    quantize_percent,
)
from app.ai.tools.errors import ToolError
from app.ai.tools.executor import ToolExecutionBudget, ToolExecutor, enforce_read_only_session
from app.ai.tools.financial_tools import register_financial_tools
from app.ai.tools.registry import (
    SchemaSecurityViolationError,
    ToolRegistry,
    assert_schema_is_secure,
    default_registry,
)
from app.db.session import Base
from app.models.borrow import BorrowAssessment
from app.models.enums import ReadinessBand, TransactionSource, TransactionType
from app.models.plan import Account, Transaction, TransactionImport
from app.models.recurring import RecurringCommitment
from app.models.user import User


@pytest.fixture
async def db_session():
    """In-memory SQLite async engine with required financial tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    User.__table__,
                    Account.__table__,
                    TransactionImport.__table__,
                    Transaction.__table__,
                    RecurringCommitment.__table__,
                    BorrowAssessment.__table__,
                ],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()

    await engine.dispose()


@pytest.fixture
def test_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_user_id() -> uuid.UUID:
    return uuid.uuid4()


# ============================================================================
# 1. Schema Security Tests
# ============================================================================


def test_registered_tool_schemas_contain_no_prohibited_fields() -> None:
    register_financial_tools()
    schemas = default_registry.export_schemas()
    assert len(schemas) >= 6

    for schema in schemas:
        fn = schema["function"]
        params = fn["parameters"]
        props = params.get("properties", {})
        # Check that user identity and SQL fields are not in properties
        for prohibited in ("user_id", "account_id", "owner_id", "sql", "raw_sql", "query_string"):
            assert prohibited not in props, f"Prohibited field '{prohibited}' found in {fn['name']}"


def test_schema_security_violation_rejection() -> None:
    bad_schema = {
        "name": "malicious_tool",
        "description": "Exploit",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
            },
        },
    }
    with pytest.raises(SchemaSecurityViolationError, match="user_id"):
        assert_schema_is_secure(bad_schema)


# ============================================================================
# 2. Math & Grounded Facts Unit Tests
# ============================================================================


def test_quantize_currency_and_percent() -> None:
    # Deterministic ROUND_HALF_UP at 2 decimal places
    assert quantize_currency(Decimal("100.505")) == Decimal("100.51")
    assert quantize_currency(100.504) == Decimal("100.50")
    assert quantize_currency("1250.00") == Decimal("1250.00")

    assert quantize_percent(Decimal("12.345")) == Decimal("12.35")
    assert quantize_percent(Decimal("12.344")) == Decimal("12.34")


def test_calculate_percentage_change_zero_baseline() -> None:
    pct, warn = calculate_percentage_change(Decimal("0.00"), Decimal("150.00"))
    assert pct is None
    assert warn is not None
    assert "zero" in warn.lower()


def test_calculate_percentage_change_valid() -> None:
    pct, warn = calculate_percentage_change(Decimal("100.00"), Decimal("150.00"))
    assert pct == Decimal("50.00")
    assert warn is None

    pct_drop, _ = calculate_percentage_change(Decimal("200.00"), Decimal("100.00"))
    assert pct_drop == Decimal("-50.00")


# ============================================================================
# 3. Read-Only Enforcement Tests
# ============================================================================


async def test_read_only_enforcement_blocks_sql_writes(db_session: AsyncSession) -> None:
    async with enforce_read_only_session(db_session):
        with pytest.raises(ToolError) as exc_info:
            await db_session.execute(text("INSERT INTO users (id, email) VALUES ('fake', 'fake')"))
        assert exc_info.value.code == "forbidden"


async def test_read_only_enforcement_blocks_orm_flush(
    db_session: AsyncSession, test_user_id: uuid.UUID
) -> None:
    async with enforce_read_only_session(db_session):
        user = User(id=test_user_id, email=f"test_{uuid.uuid4().hex[:6]}@example.com")
        db_session.add(user)
        with pytest.raises(ToolError) as exc_info:
            await db_session.flush()
        assert exc_info.value.code == "forbidden"


async def test_executor_blocks_unauthorized_write_tool(
    db_session: AsyncSession, test_user_id: uuid.UUID
) -> None:
    class DummyInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class DummyOutput(BaseModel):
        pass

    async def bad_handler(ctx: ToolContext, args: DummyInput) -> ToolResult:
        await ctx.session.execute(text("INSERT INTO users (id, email) VALUES ('bad', 'bad')"))
        return ToolResult(ok=True, tool="bad_tool", data={})

    bad_tool = Tool(
        name="bad_tool",
        description="Attempts write",
        input_model=DummyInput,
        output_model=DummyOutput,
        handler=bad_handler,
    )
    reg = ToolRegistry()
    reg.register(bad_tool)
    executor = ToolExecutor(registry=reg)

    ctx = ToolContext(user_id=test_user_id, request_id="bad_req", session=db_session)
    with pytest.raises(ToolError) as exc_info:
        await executor.execute("bad_tool", {}, ctx)
    assert exc_info.value.code == "forbidden"


# ============================================================================
# 4. Financial Tools Functional Tests
# ============================================================================


async def _seed_test_financial_data(
    session: AsyncSession,
    user_id: uuid.UUID,
    other_user_id: uuid.UUID,
) -> None:
    # Users
    u1 = User(
        id=user_id,
        email="u1@example.com",
        normalized_email="u1@example.com",
        hashed_password="mock_hashed_pw",
        full_name="User One",
    )
    u2 = User(
        id=other_user_id,
        email="u2@example.com",
        normalized_email="u2@example.com",
        hashed_password="mock_hashed_pw",
        full_name="User Two",
    )
    session.add_all([u1, u2])
    await session.flush()

    # Accounts
    acc1 = Account(
        id=uuid.uuid4(),
        user_id=user_id,
        name="Primary Savings",
        institution_name="HDFC Bank",
        account_number_mask="****1234",
    )
    acc2 = Account(
        id=uuid.uuid4(),
        user_id=other_user_id,
        name="Other Savings",
        institution_name="ICICI Bank",
        account_number_mask="****5678",
    )
    session.add_all([acc1, acc2])
    await session.flush()

    # Transactions for user 1
    base_date = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    txns = [
        # User 1 income
        Transaction(
            user_id=user_id,
            account_id=acc1.id,
            transaction_date=base_date,
            amount=Decimal("50000.00"),
            transaction_type=TransactionType.CREDIT,
            category="Salary",
            description="Monthly Salary",
            description_cleaned="monthly salary",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        ),
        # User 1 expenses
        Transaction(
            user_id=user_id,
            account_id=acc1.id,
            transaction_date=base_date + timedelta(days=1),
            amount=Decimal("12000.00"),
            transaction_type=TransactionType.DEBIT,
            category="Rent",
            description="House Rent",
            description_cleaned="house rent",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        ),
        Transaction(
            user_id=user_id,
            account_id=acc1.id,
            transaction_date=base_date + timedelta(days=2),
            amount=Decimal("4500.00"),
            transaction_type=TransactionType.DEBIT,
            category="Groceries",
            description="Supermarket",
            description_cleaned="supermarket",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        ),
        Transaction(
            user_id=user_id,
            account_id=acc1.id,
            transaction_date=base_date + timedelta(days=3),
            amount=Decimal("1500.00"),
            transaction_type=TransactionType.DEBIT,
            category="Dining",
            description="Restaurant",
            description_cleaned="restaurant",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        ),
        # Transfer - should be excluded from spending and income
        Transaction(
            user_id=user_id,
            account_id=acc1.id,
            transaction_date=base_date + timedelta(days=4),
            amount=Decimal("10000.00"),
            transaction_type=TransactionType.DEBIT,
            category="Transfers",
            description="Self transfer to wallet",
            description_cleaned="self transfer to wallet",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        ),
        # Other user's transaction - should NEVER be counted
        Transaction(
            user_id=other_user_id,
            account_id=acc2.id,
            transaction_date=base_date,
            amount=Decimal("99999.00"),
            transaction_type=TransactionType.DEBIT,
            category="Luxury",
            description="Other user spend",
            description_cleaned="other user spend",
            normalized_fingerprint=uuid.uuid4().hex,
            source=TransactionSource.CSV_UPLOAD,
        ),
    ]
    session.add_all(txns)

    # Recurring commitments for user 1
    recurrings = [
        RecurringCommitment(
            user_id=user_id,
            name="Netflix Subscription",
            category="Entertainment",
            amount_type="fixed",
            expected_amount=Decimal("649.00"),
            frequency="monthly",
            due_rule_day=5,
            is_active=True,
        ),
        RecurringCommitment(
            user_id=user_id,
            name="Gym Membership",
            category="Health",
            amount_type="fixed",
            expected_amount=Decimal("3000.00"),
            frequency="quarterly",
            due_rule_day=1,
            is_active=True,
        ),
    ]
    session.add_all(recurrings)
    await session.commit()


async def test_get_spending_summary(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
    other_user_id: uuid.UUID,
) -> None:
    await _seed_test_financial_data(db_session, test_user_id, other_user_id)
    ctx = ToolContext(user_id=test_user_id, request_id="req_1", session=db_session)
    executor = ToolExecutor()

    result = await executor.execute(
        "get_spending_summary",
        {"start_date": "2026-01-01", "end_date": "2026-01-31"},
        ctx,
    )

    assert result.ok is True
    data = result.data
    # Debits: 12000 (Rent) + 4500 (Groceries) + 1500 (Dining) = 18000.00. (Transfers 10000 excluded)
    assert data["total_spent"] == Decimal("18000.00")
    # Income: 50000.00
    assert data["total_income"] == Decimal("50000.00")
    assert data["net_cash_flow"] == Decimal("32000.00")
    # Total txns for user1 in range: 5 (including transfer)
    assert data["transaction_count"] == 5

    # Check facts
    fact_map = {f.id: f for f in result.facts}
    assert fact_map["total_spent"].value == "18000.00"
    assert fact_map["total_income"].value == "50000.00"
    assert fact_map["net_cash_flow"].value == "32000.00"


async def test_get_category_breakdown(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
    other_user_id: uuid.UUID,
) -> None:
    await _seed_test_financial_data(db_session, test_user_id, other_user_id)
    ctx = ToolContext(user_id=test_user_id, request_id="req_2", session=db_session)
    executor = ToolExecutor()

    result = await executor.execute(
        "get_category_breakdown",
        {"start_date": "2026-01-01", "end_date": "2026-01-31", "top_n": 2},
        ctx,
    )

    assert result.ok is True
    data = result.data
    assert data["total_spending"] == Decimal("18000.00")
    # Top 2 categories: Rent (12000) and Groceries (4500)
    cats = data["categories"]
    assert len(cats) == 2
    assert cats[0]["category"] == "Rent"
    assert cats[0]["total_amount"] == Decimal("12000.00")
    assert cats[0]["percentage_of_total"] == Decimal("66.67")

    assert cats[1]["category"] == "Groceries"
    assert cats[1]["total_amount"] == Decimal("4500.00")
    assert cats[1]["percentage_of_total"] == Decimal("25.00")

    # Remaining category: Dining (1500) into other_amount
    assert data["other_amount"] == Decimal("1500.00")
    assert data["other_percentage"] == Decimal("8.33")


async def test_compare_periods(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
    other_user_id: uuid.UUID,
) -> None:
    await _seed_test_financial_data(db_session, test_user_id, other_user_id)
    ctx = ToolContext(user_id=test_user_id, request_id="req_3", session=db_session)
    executor = ToolExecutor()

    # Compare Jan 2026 (spending 18000) with Feb 2026 (spending 0)
    result = await executor.execute(
        "compare_periods",
        {
            "period_a_start": "2026-01-01",
            "period_a_end": "2026-01-31",
            "period_b_start": "2026-02-01",
            "period_b_end": "2026-02-28",
        },
        ctx,
    )

    assert result.ok is True
    data = result.data
    assert data["spending_difference"] == Decimal("-18000.00")
    assert data["spending_percentage_change"] == Decimal("-100.00")
    # Duration mismatch: 31 vs 28 days
    assert data["duration_mismatch_warning"] is not None


async def test_get_cash_flow(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
    other_user_id: uuid.UUID,
) -> None:
    await _seed_test_financial_data(db_session, test_user_id, other_user_id)
    ctx = ToolContext(user_id=test_user_id, request_id="req_4", session=db_session)
    executor = ToolExecutor()

    result = await executor.execute(
        "get_cash_flow",
        {"start_date": "2026-01-01", "end_date": "2026-01-31", "granularity": "monthly"},
        ctx,
    )

    assert result.ok is True
    data = result.data
    assert data["total_inflow"] == Decimal("50000.00")
    assert data["total_outflow"] == Decimal("18000.00")
    assert len(data["buckets"]) == 1
    assert data["buckets"][0]["net"] == Decimal("32000.00")


async def test_list_recurring_payments(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
    other_user_id: uuid.UUID,
) -> None:
    await _seed_test_financial_data(db_session, test_user_id, other_user_id)
    ctx = ToolContext(user_id=test_user_id, request_id="req_5", session=db_session)
    executor = ToolExecutor()

    result = await executor.execute("list_recurring_payments", {"is_active": True}, ctx)

    assert result.ok is True
    data = result.data
    assert data["active_count"] == 2
    # Netflix (649 monthly) + Gym (3000 quarterly = 1000/mo) = 1649.00
    assert data["total_monthly_committed"] == Decimal("1649.00")


async def test_get_borrow_readiness_no_score_invented(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
) -> None:
    # 1. No assessment in DB
    ctx = ToolContext(user_id=test_user_id, request_id="req_6", session=db_session)
    executor = ToolExecutor()

    res_missing = await executor.execute("get_borrow_readiness", {"refresh": False}, ctx)
    assert res_missing.ok is True
    assert res_missing.data["status"] == "insufficient_data"
    assert res_missing.data["readiness_band"] is None
    # Must NOT invent any score
    for f in res_missing.facts:
        assert "score" not in f.id.lower()

    # 2. Add real assessment
    assessment = BorrowAssessment(
        user_id=test_user_id,
        model_version="v1.0",
        feature_version="f1.0",
        default_probability=Decimal("0.0450"),
        readiness_band=ReadinessBand.GOOD,
        top_factors=[{"factor": "Low credit utilization", "impact": "positive"}],
        recommendations=["Maintain low credit card balance"],
        input_features={"dti": 0.2},
    )
    db_session.add(assessment)
    await db_session.commit()

    res_present = await executor.execute("get_borrow_readiness", {"refresh": False}, ctx)
    assert res_present.ok is True
    assert res_present.data["status"] == "available"
    assert res_present.data["readiness_band"] == "good"
    assert len(res_present.data["top_factors"]) == 1

    # Verify facts only contain the band, never a numerical credit score or default_probability
    assert len(res_present.facts) == 1
    assert res_present.facts[0].id == "readiness_band"
    assert res_present.facts[0].value == "good"


# ============================================================================
# 5. ToolExecutor Limits and Safety Tests
# ============================================================================


async def test_executor_rejects_extra_arguments(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
) -> None:
    ctx = ToolContext(user_id=test_user_id, request_id="req_7", session=db_session)
    executor = ToolExecutor()

    # extra='forbid' prevents passing unauthorized fields like user_id or random params
    with pytest.raises(ToolError) as exc_info:
        await executor.execute(
            "get_spending_summary",
            {"start_date": "2026-01-01", "end_date": "2026-01-31", "user_id": str(uuid.uuid4())},
            ctx,
        )
    assert exc_info.value.code == "invalid_arguments"


async def test_executor_rejects_unknown_tool(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
) -> None:
    ctx = ToolContext(user_id=test_user_id, request_id="req_8", session=db_session)
    executor = ToolExecutor()

    with pytest.raises(ToolError) as exc_info:
        await executor.execute("non_existent_tool", {}, ctx)
    assert exc_info.value.code == "not_found"


async def test_executor_enforces_budget_limits(
    db_session: AsyncSession,
    test_user_id: uuid.UUID,
) -> None:
    ctx = ToolContext(user_id=test_user_id, request_id="req_9", session=db_session)
    executor = ToolExecutor()
    budget = ToolExecutionBudget(max_tool_calls=2)

    await executor.execute("get_borrow_readiness", {}, ctx, budget=budget)
    await executor.execute("get_borrow_readiness", {}, ctx, budget=budget)

    # 3rd call exceeds max_tool_calls=2
    with pytest.raises(ToolError) as exc_info:
        await executor.execute("get_borrow_readiness", {}, ctx, budget=budget)
    assert exc_info.value.code == "limit_exceeded"
