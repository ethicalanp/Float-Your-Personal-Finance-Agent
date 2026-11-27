import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import ToolContext
from app.ai.tools.financial_tools import register_financial_tools
from app.ai.tools.registry import default_registry
from app.models.budget import DEFAULT_CATEGORY_MAPPINGS, BudgetPlan
from app.models.recurring import RecurringCommitment, RecurringOccurrence
from app.models.user import User


def test_budget_recurring_tools_registered_and_secure() -> None:
    register_financial_tools()
    names = {t.name for t in default_registry.list_tools()}
    assert "get_budget_plan" in names
    assert "get_recurring_payments" in names
    assert "get_upcoming_bills" in names

    # Must pass assert_schema_is_secure (no user_id, account_id, or SQL fields)
    schemas = default_registry.export_schemas()
    exported_names = {s["function"]["name"] for s in schemas}
    assert {"get_budget_plan", "get_recurring_payments", "get_upcoming_bills"}.issubset(exported_names)


@pytest.mark.asyncio
async def test_budget_recurring_tools_execution_and_eval_cases(db_session: AsyncSession) -> None:
    register_financial_tools()
    uid = uuid.uuid4()
    user = User(id=uid, email=f"tool_{uid.hex[:8]}@example.com", password_hash="hashed", full_name="Tool User")
    db_session.add(user)
    await db_session.flush()

    plan = BudgetPlan(
        user_id=uid,
        month="2026-11",
        version=1,
        is_current=True,
        monthly_income_paise=10_000_000,
        extra_income_paise=0,
        income_mode="fixed",
        irregular_months=3,
        needs_pct=50,
        wants_pct=30,
        savings_pct=20,
        needs_paise=5_000_000,
        wants_paise=3_000_000,
        savings_paise=2_000_000,
        category_mappings=dict(DEFAULT_CATEGORY_MAPPINGS),
    )
    db_session.add(plan)

    comm = RecurringCommitment(
        user_id=uid,
        name="Broadband",
        category="Utilities",
        expected_amount=999,
        frequency="monthly",
        due_rule_day=5,
        merchant="Airtel",
        is_active=True,
    )
    db_session.add(comm)
    await db_session.flush()

    occ = RecurringOccurrence(
        commitment_id=comm.id,
        user_id=uid,
        due_date=date.today() + timedelta(days=2),
        expected_amount=999,
        status="upcoming",
    )
    db_session.add(occ)
    await db_session.commit()

    ctx = ToolContext(user_id=uid, session=db_session)

    # Eval case 1: get_budget_plan with explicit month
    bp_tool = default_registry.get("get_budget_plan")
    bp_args = bp_tool.input_model.model_validate({"month": "2026-11"})
    bp_res = await bp_tool.handler(ctx, bp_args)
    assert bp_res.data["has_plan"] is True
    assert str(bp_res.data["needs_inr"]) == "50000.00"
    assert len(bp_res.facts) == 3

    # Eval case 2: get_recurring_payments
    rp_tool = default_registry.get("get_recurring_payments")
    rp_args = rp_tool.input_model.model_validate({"is_active": True})
    rp_res = await rp_tool.handler(ctx, rp_args)
    assert rp_res.data["total_active_count"] == 1

    # Eval case 3: get_upcoming_bills
    ub_tool = default_registry.get("get_upcoming_bills")
    ub_args = ub_tool.input_model.model_validate({"days_ahead": 7})
    ub_res = await ub_tool.handler(ctx, ub_args)
    assert ub_res.data["due_soon_count"] == 1
    assert ub_res.bills if hasattr(ub_res, "bills") else ub_res.data["bills"][0]["name"] == "Broadband"
