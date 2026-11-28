import uuid

import pytest

from app.ai.agent.models import RouteClass
from app.ai.agent.planner import ALLOWED_TOOL_CATALOGUE, create_deterministic_plan
from app.ai.tools.base import ToolContext
from app.ai.tools.financial_tools import HealthScoreInput, handle_get_health_score, register_financial_tools
from app.ai.tools.registry import default_registry
from app.models.user import User


def test_get_health_score_registered_and_no_user_id_in_schema() -> None:
    register_financial_tools()
    tool = default_registry.get("get_health_score")
    assert tool is not None
    assert "get_health_score" in ALLOWED_TOOL_CATALOGUE
    schema_props = tool.input_model.model_json_schema().get("properties", {})
    assert "user_id" not in schema_props


def test_deterministic_planner_routes_health_score_queries() -> None:
    plan = create_deterministic_plan(RouteClass.PERSONAL_FINANCE, "What is my Float financial health score?")
    assert any(tc.tool_name == "get_health_score" for tc in plan.tool_calls)


@pytest.mark.asyncio
async def test_get_health_score_tool_returns_insufficient_data_without_zeros(client) -> None:
    from app.db.session import get_async_session_factory

    factory = get_async_session_factory()
    async with factory() as db_session:
        user = User(
            id=uuid.uuid4(),
            email="hst_tool@example.com",
            normalized_email="hst_tool@example.com",
            full_name="HS Tool",
        )
        db_session.add(user)
        await db_session.commit()

        ctx = ToolContext(user_id=user.id, session=db_session, request_id="req-test-1")
        res = await handle_get_health_score(ctx, HealthScoreInput())
        assert res.ok is True
        assert res.tool == "get_health_score"
        assert res.data["band"] == "insufficient_data"
        assert res.data["overall_score"] is None
        fact_ids = {f.id for f in res.facts}
        assert {"health_formula_version", "health_band", "health_available_components"}.issubset(fact_ids)
