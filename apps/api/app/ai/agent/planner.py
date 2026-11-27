import logging
import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.agent.models import OrchestratorPlan, RouteClass, ToolCallSpec
from app.ai.agent.router import IntentRouter
from app.ai.gateway.errors import CircuitOpen, RateLimited, Timeout, TransientProviderError
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.types import LLMMessage, LLMRequest
from app.ai.mcp.tools import (
    CheckScamInput,
    DraftComplaintInput,
    GetVerifiedContactsInput,
    SearchKnowledgeInput,
)
from app.ai.tools.financial_tools import (
    BorrowReadinessInput,
    BudgetPlanInput,
    CashFlowInput,
    CategoryBreakdownInput,
    ComparePeriodsInput,
    ListRecurringPaymentsInput,
    SpendingSummaryInput,
)
from app.models.protect import AuditTrail

logger = logging.getLogger("app.ai.agent.planner")

ALLOWED_TOOL_CATALOGUE = {
    "get_spending_summary": SpendingSummaryInput,
    "get_category_breakdown": CategoryBreakdownInput,
    "compare_periods": ComparePeriodsInput,
    "get_cash_flow": CashFlowInput,
    "list_recurring_payments": ListRecurringPaymentsInput,
    "get_borrow_readiness": BorrowReadinessInput,
    "get_budget_plan": BudgetPlanInput,
    "check_scam_message": CheckScamInput,
    "draft_complaint": DraftComplaintInput,
    "get_verified_contacts": GetVerifiedContactsInput,
    "search_knowledge": SearchKnowledgeInput,
}

MAX_STEPS = 4
MAX_TOOL_CALLS = 4
DEFAULT_TIME_BUDGET_SECONDS = 8.0

PLANNER_SYSTEM_PROMPT = """You are Float's Planning Agent for personal finance, scam protection, and borrowing guidance.
You MUST propose a concise, valid JSON plan to address the user inquiry using ONLY the tools from the allowed catalogue:
1. get_spending_summary(start_date, end_date)
2. get_category_breakdown(start_date, end_date, top_n)
3. compare_periods(period_a_start, period_a_end, period_b_start, period_b_end)
4. get_cash_flow(start_date, end_date, bucket)
5. list_recurring_payments()
6. get_borrow_readiness(as_of_date)
7. check_scam_message(message)
8. draft_complaint(bank_name, account_number_mask, transaction_reference,
   transaction_amount, incident_date, description)
9. get_verified_contacts(category, search_query)
10. search_knowledge(query, language, top_k)
11. get_budget_plan(month)

Rules:
- Maximum 4 steps total.
- Maximum 4 tool calls total.
- Never invent tool names or tool parameters.
- Provide output strictly adhering to the JSON schema."""


class PlannedStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str = Field(description="Name of the tool from the allowed catalogue")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Typed arguments for the tool")
    rationale: str | None = Field(default=None, description="One-sentence reason for this step")


class AgentPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rationale: str = Field(description="Brief planning rationale")
    steps: list[PlannedStep] = Field(default_factory=list, description="Planned sequential steps (max 4)")
    needs_knowledge_retrieval: bool = Field(default=False)
    knowledge_query: str | None = Field(default=None)


class PlannerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: OrchestratorPlan
    fallback_used: bool = False
    fallback_reason: str | None = None


class StepExecutionRecord(BaseModel):
    step_index: int
    tool_name: str
    arguments_summary: dict[str, Any]
    duration_ms: float
    status: str
    error: str | None = None


class AgentTrace(BaseModel):
    trace_id: str
    run_id: str
    user_id: str
    created_at: float
    status: str
    fallback_used: bool
    fallback_reason: str | None = None
    steps: list[StepExecutionRecord] = Field(default_factory=list)
    duration_ms: float
    validation_results: dict[str, bool] = Field(default_factory=dict)



# In-memory store for traces
_TRACE_STORE: dict[str, dict[str, Any]] = {}


def record_agent_trace(trace: AgentTrace) -> None:
    """Store trace record without raw financial amounts or raw user PII."""
    _TRACE_STORE[trace.trace_id] = trace.model_dump()


async def get_agent_trace(
    trace_id: str,
    user_id: str,
    session: AsyncSession | Session | None = None,
) -> dict[str, Any] | None:
    """Retrieve trace ensuring user isolation."""
    trace_data = _TRACE_STORE.get(trace_id)
    if trace_data:
        if str(trace_data.get("user_id")) != str(user_id):
            return None
        return trace_data

    if session is not None:
        try:
            stmt = select(AuditTrail).where(
                AuditTrail.resource_type == "agent_trace",
                AuditTrail.resource_id == trace_id,
            )
            if isinstance(session, AsyncSession):
                res = await session.execute(stmt)
                entry = res.scalar_one_or_none()
            else:
                entry = session.execute(stmt).scalar_one_or_none()
            if entry and str(entry.user_id) == str(user_id):
                return entry.metadata_json
        except Exception:
            pass

    return None


def summarize_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Summarize tool arguments stripping exact monetary amounts and raw text for safe audit."""
    summary: dict[str, Any] = {"tool": tool_name}
    for k, v in args.items():
        if "date" in k:
            summary[k] = str(v)
        elif "amount" in k:
            summary[k] = "<amount_provided>"
        elif "message" in k or "text" in k or "description" in k or "query" in k:
            summary[k] = f"<{len(str(v))} chars masked text>"
        elif "account" in k or "reference" in k:
            summary[k] = "<masked_ref>"
        else:
            summary[k] = str(v)[:30]
    return summary


def create_deterministic_plan(route: RouteClass, query: str) -> OrchestratorPlan:
    """Build a deterministic fallback plan from detected route and query keywords."""
    q_lower = query.lower()
    today = date.today()
    start_date = date(today.year, today.month, 1)
    end_date = today

    tool_calls: list[ToolCallSpec] = []
    needs_retrieval = False
    retrieval_query = None

    if route == RouteClass.PERSONAL_FINANCE:
        if any(w in q_lower for w in ("recurring", "subscription", "bills")):
            tool_calls.append(ToolCallSpec(tool_name="list_recurring_payments", arguments={"is_active": True}))
        elif any(w in q_lower for w in ("category", "breakdown", "categories")):
            tool_calls.append(
                ToolCallSpec(
                    tool_name="get_category_breakdown",
                    arguments={"start_date": str(start_date), "end_date": str(end_date), "top_n": 5},
                )
            )
        elif any(w in q_lower for w in ("cash flow", "trend", "monthly flow", "inflow")):
            tool_calls.append(
                ToolCallSpec(
                    tool_name="get_cash_flow",
                    arguments={"start_date": str(start_date), "end_date": str(end_date), "bucket": "monthly"},
                )
            )
        elif any(w in q_lower for w in ("budget", "50/30/20", "split")):
            tool_calls.append(ToolCallSpec(tool_name="get_budget_plan", arguments={}))
        else:
            tool_calls.append(
                ToolCallSpec(
                    tool_name="get_spending_summary",
                    arguments={"start_date": str(start_date), "end_date": str(end_date)},
                )
            )

    elif route == RouteClass.CREDIT_READINESS:
        tool_calls.append(ToolCallSpec(tool_name="get_borrow_readiness", arguments={}))

    elif route == RouteClass.PROTECT:
        if any(w in q_lower for w in ("helpline", "portal", "contact", "phone", "number")):
            tool_calls.append(ToolCallSpec(tool_name="get_verified_contacts", arguments={"category": "all"}))
        elif any(w in q_lower for w in ("draft", "complaint", "dispute")):
            tool_calls.append(
                ToolCallSpec(
                    tool_name="draft_complaint",
                    arguments={
                        "bank_name": "Bank",
                        "account_number_mask": "XXXX-1234",
                        "transaction_reference": "TXN123456",
                        "transaction_amount": 5000.0,
                    },
                )
            )
        elif any(w in q_lower for w in ("alert", "disconnect", "urgent", "link", "kyc", "block")):
            tool_calls.append(ToolCallSpec(tool_name="check_scam_message", arguments={"message": query}))
        needs_retrieval = True
        retrieval_query = query

    elif route == RouteClass.KNOWLEDGE:
        tool_calls.append(ToolCallSpec(tool_name="search_knowledge", arguments={"query": query, "top_k": 3}))
        needs_retrieval = True
        retrieval_query = query

    elif route == RouteClass.COMBINED:
        tool_calls.append(
            ToolCallSpec(
                tool_name="get_spending_summary",
                arguments={"start_date": str(start_date), "end_date": str(end_date)},
            )
        )
        needs_retrieval = True
        retrieval_query = query

    return OrchestratorPlan(
        route=route,
        tool_calls=tool_calls,
        needs_retrieval=needs_retrieval,
        retrieval_query=retrieval_query,
    )


class AgentPlanner:
    """Proposes and validates multi-step plans with strict bounded limits and fallback to deterministic router."""

    def __init__(
        self,
        gateway: LLMGateway,
        router: IntentRouter,
        time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    ) -> None:
        self.gateway = gateway
        self.router = router
        self.time_budget_seconds = time_budget_seconds

    def validate_plan(self, plan: AgentPlanOutput) -> tuple[bool, str | None]:
        """Validate proposed plan against allowed catalogue, step limits, and input schemas."""
        if len(plan.steps) > MAX_STEPS:
            return False, f"Step limit exceeded: proposed {len(plan.steps)} steps (max {MAX_STEPS})"

        if len(plan.steps) > MAX_TOOL_CALLS:
            return False, f"Tool calls limit exceeded: proposed {len(plan.steps)} tool calls (max {MAX_TOOL_CALLS})"

        for idx, step in enumerate(plan.steps):
            if step.tool_name not in ALLOWED_TOOL_CATALOGUE:
                return False, f"Step {idx + 1}: Tool '{step.tool_name}' not in allowed catalogue"

            input_cls: Any = ALLOWED_TOOL_CATALOGUE[step.tool_name]
            try:
                input_cls.model_validate(step.arguments)
            except ValidationError as ve:
                return False, f"Step {idx + 1}: Invalid arguments for '{step.tool_name}': {ve}"

        return True, None

    async def plan(
        self,
        masked_question: str,
        user_id: str,
        trace_id: str | None = None,
        default_route: RouteClass | None = None,
    ) -> PlannerResult:
        """Generate a plan via LLM or return deterministic fallback route."""
        trace_id = trace_id or str(uuid.uuid4())

        llm_messages = [
            LLMMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=(
                    f"User Inquiry: {masked_question}\n"
                    f"Construct a valid plan using allowed tools. Keep it under {MAX_STEPS} steps."
                ),
            ),
        ]

        llm_req = LLMRequest(
            messages=llm_messages,
            response_schema=AgentPlanOutput,
            temperature=0.0,
            max_output_tokens=500,
            prompt_version="planner_v1",
            trace_id=trace_id,
            user_id=user_id,
            data_class="masked_real",
        )

        try:
            llm_resp = await self.gateway.complete(llm_req)
            if isinstance(llm_resp.parsed, AgentPlanOutput):
                plan_out = llm_resp.parsed
            elif isinstance(llm_resp.parsed, dict):
                plan_out = AgentPlanOutput.model_validate(llm_resp.parsed)
            else:
                raise ValueError("Planner output could not be parsed as AgentPlanOutput")

            # Validate plan constraints
            is_valid, validation_err = self.validate_plan(plan_out)
            if not is_valid:
                logger.warning("Proposed plan invalid (%s), falling back to deterministic router", validation_err)
                fallback_route = default_route or (await self.router.route(masked_question)).route
                det_plan = create_deterministic_plan(fallback_route, masked_question)
                return PlannerResult(plan=det_plan, fallback_used=True, fallback_reason=validation_err)

            # Valid plan -> convert to OrchestratorPlan
            tool_calls = [
                ToolCallSpec(tool_name=s.tool_name, arguments=s.arguments)
                for s in plan_out.steps
            ]
            orch_plan = OrchestratorPlan(
                route=default_route or (RouteClass.COMBINED if len(tool_calls) > 1 else RouteClass.PERSONAL_FINANCE),
                tool_calls=tool_calls,
                needs_retrieval=plan_out.needs_knowledge_retrieval,
                retrieval_query=plan_out.knowledge_query,
            )
            return PlannerResult(plan=orch_plan, fallback_used=False, fallback_reason=None)

        except (CircuitOpen, RateLimited, Timeout, TransientProviderError, Exception) as exc:
            reason = f"LLMPlannerUnavailable({type(exc).__name__})"
            logger.warning("Planner LLM failed (%s), falling back to deterministic router", reason)
            fallback_route = default_route or (await self.router.route(masked_question)).route
            det_plan = create_deterministic_plan(fallback_route, masked_question)
            return PlannerResult(plan=det_plan, fallback_used=True, fallback_reason=reason)
