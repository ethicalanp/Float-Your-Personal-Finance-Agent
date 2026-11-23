import pytest

from app.ai.agent.models import RouteClass
from app.ai.agent.planner import (
    ALLOWED_TOOL_CATALOGUE,
    MAX_TOOL_CALLS,
    AgentPlanner,
    AgentPlanOutput,
    PlannedStep,
    summarize_arguments,
)
from app.ai.agent.router import IntentRouter
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.manager import LLMGateway


@pytest.fixture
def fake_gateway() -> LLMGateway:
    return LLMGateway(
        config=LLMConfig(provider="fake", approved_for_real_data=True),
        adapter=FakeProvider(),
    )


@pytest.fixture
def planner(fake_gateway: LLMGateway) -> AgentPlanner:
    router = IntentRouter(gateway=fake_gateway)
    return AgentPlanner(gateway=fake_gateway, router=router)


def test_allowed_tool_catalogue_contains_10_tools() -> None:
    """Verify exactly 10 registered tools in the planning catalogue."""
    assert len(ALLOWED_TOOL_CATALOGUE) == 10
    expected = [
        "get_spending_summary",
        "get_category_breakdown",
        "compare_periods",
        "get_cash_flow",
        "list_recurring_payments",
        "get_borrow_readiness",
        "check_scam_message",
        "draft_complaint",
        "get_verified_contacts",
        "search_knowledge",
    ]
    for tool_name in expected:
        assert tool_name in ALLOWED_TOOL_CATALOGUE


def test_validate_plan_enforces_max_steps(planner: AgentPlanner) -> None:
    """Verify that any plan proposing >4 steps is rejected."""
    excessive_steps = [
        PlannedStep(tool_name="get_spending_summary", arguments={}),
        PlannedStep(tool_name="get_cash_flow", arguments={}),
        PlannedStep(tool_name="list_recurring_payments", arguments={}),
        PlannedStep(tool_name="get_borrow_readiness", arguments={}),
        PlannedStep(tool_name="search_knowledge", arguments={"query": "test"}),
    ]
    plan = AgentPlanOutput(rationale="5 steps", steps=excessive_steps)
    valid, err = planner.validate_plan(plan)
    assert not valid
    assert "Step limit exceeded" in (err or "")


def test_validate_plan_rejects_unknown_tools(planner: AgentPlanner) -> None:
    """Verify that plans proposing unauthorized tools are rejected."""
    plan = AgentPlanOutput(
        rationale="Unknown tool",
        steps=[PlannedStep(tool_name="delete_all_transactions", arguments={})],
    )
    valid, err = planner.validate_plan(plan)
    assert not valid
    assert "not in allowed catalogue" in (err or "")


def test_validate_plan_accepts_valid_steps(planner: AgentPlanner) -> None:
    """Verify that compliant plans with valid arguments pass validation."""
    plan = AgentPlanOutput(
        rationale="Monthly review",
        steps=[
            PlannedStep(
                tool_name="get_cash_flow",
                arguments={"start_date": "2026-11-01", "end_date": "2026-11-30", "granularity": "monthly"},
            ),
        ],
    )
    valid, err = planner.validate_plan(plan)
    assert valid
    assert err is None


def test_summarize_arguments_masks_amounts_and_text() -> None:
    """Verify that summarize_arguments removes exact monetary amounts and raw text."""
    raw_args = {
        "start_date": "2026-11-01",
        "end_date": "2026-11-30",
        "transaction_amount": 145000.50,
        "message": "URGENT OTP 999123 click here",
        "account_number_mask": "XXXX-9999",
    }
    summary = summarize_arguments("draft_complaint", raw_args)

    assert summary["start_date"] == "2026-11-01"
    assert summary["transaction_amount"] == "<amount_provided>"
    assert "<masked_ref>" in summary["account_number_mask"]
    assert "chars masked text" in summary["message"]
    assert "145000" not in str(summary)
    assert "999123" not in str(summary)


@pytest.mark.asyncio
async def test_planner_fallback_on_invalid_plan(planner: AgentPlanner) -> None:
    """Verify that planner falls back cleanly to deterministic router on error or invalid plan."""
    res = await planner.plan(
        masked_question="What is my spending this month?",
        user_id="00000000-0000-0000-0000-000000000001",
        default_route=RouteClass.PERSONAL_FINANCE,
    )
    assert res.plan is not None
    assert len(res.plan.tool_calls) <= MAX_TOOL_CALLS
