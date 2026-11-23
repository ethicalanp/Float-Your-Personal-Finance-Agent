import logging
import re
import time
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.agent.composer import ResponseComposer, build_structured_fallback
from app.ai.agent.models import (
    AgentState,
    AssistantChatRequest,
    AssistantChatResponse,
    OrchestratorPlan,
    RouteClass,
    ToolCallSpec,
)
from app.ai.agent.numeric_grounding import NumericGroundingValidator
from app.ai.agent.planner import (
    AgentPlanner,
    AgentTrace,
    StepExecutionRecord,
    record_agent_trace,
    summarize_arguments,
)
from app.ai.agent.router import IntentRouter, detect_query_language
from app.ai.gateway.manager import LLMGateway
from app.ai.observability.metrics import assistant_metrics
from app.ai.rag.answer_models import Citation
from app.ai.rag.dependencies import get_embedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.ai.rag.validator import AnswerValidator
from app.ai.security.masking import mask_pii
from app.ai.tools.base import Fact, ToolContext
from app.ai.tools.errors import ToolError
from app.ai.tools.executor import ToolExecutionBudget, ToolExecutor
from app.ai.tools.registry import default_registry
from app.core.errors import ForbiddenException, NotFoundException
from app.models.conversations import Conversation, Message
from app.models.enums import AuditActor, ConsentType, MessageRole
from app.models.protect import AuditTrail
from app.models.user import Consent, User

logger = logging.getLogger("app.ai.agent.orchestrator")


class AssistantOrchestrator:
    """Explicit, testable state-machine orchestrator coordinating routing, tools, RAG, and composition."""

    def __init__(
        self,
        session: AsyncSession | Session,
        gateway: LLMGateway,
        executor: ToolExecutor | None = None,
        retriever: HybridRetriever | None = None,
        router: IntentRouter | None = None,
        planner: AgentPlanner | None = None,
    ) -> None:
        self.session = session
        self.gateway = gateway
        self.executor = executor or ToolExecutor(registry=default_registry)
        self.retriever = retriever or HybridRetriever(
            session=session,
            embedder=get_embedder(),
            config=RetrievalConfig(),
        )
        self.router = router or IntentRouter(gateway=gateway)
        self.planner = planner or AgentPlanner(gateway=gateway, router=self.router)
        self.grounding_validator = NumericGroundingValidator()
        self.answer_validator = AnswerValidator()
        self.composer = ResponseComposer(gateway=gateway)

    async def run(
        self,
        request: AssistantChatRequest,
        user: User,
        trace_id: str | None = None,
    ) -> AssistantChatResponse:
        trace_id = trace_id or str(uuid.uuid4())
        start_time = time.monotonic()
        prompt_version = "agent_orchestrator_v1"

        state = AgentState.RECEIVED
        tools_called: list[str] = []
        validation_outcomes: dict[str, Any] = {}
        degraded = False

        # --------------------------------------------------------------------
        # 1. CONSENT_CHECK
        # --------------------------------------------------------------------
        state = AgentState.CONSENT_CHECK
        consent_query = select(Consent).where(
            Consent.user_id == user.id,
            Consent.consent_type == ConsentType.AI_DATA_PROCESSING,
            Consent.revoked_at.is_(None),
        )
        if isinstance(self.session, AsyncSession):
            c_res = await self.session.execute(consent_query)
        else:
            c_res = self.session.execute(consent_query)
        has_consent = c_res.scalars().first() is not None

        if not has_consent:
            return AssistantChatResponse(
                status="refusal",
                answer="AI data processing consent is required to use the personal finance assistant.",
                language="en",
                route=RouteClass.OUT_OF_SCOPE,
                confidence="high",
                degraded=False,
                trace_id=trace_id,
                prompt_version=prompt_version,
            )

        # Validate conversation ownership if conversation_id was provided
        if request.conversation_id:
            conv_stmt = select(Conversation).where(Conversation.id == request.conversation_id)
            if isinstance(self.session, AsyncSession):
                c_conv = await self.session.execute(conv_stmt)
            else:
                c_conv = self.session.execute(conv_stmt)
            conv = c_conv.scalar_one_or_none()
            if not conv:
                raise NotFoundException(f"Conversation {request.conversation_id} not found")
            if conv.user_id != user.id:
                raise ForbiddenException("Access to this conversation is forbidden")

        # --------------------------------------------------------------------
        # 2. MASK
        # --------------------------------------------------------------------
        state = AgentState.MASK
        masked_query = mask_pii(request.question)
        lang = detect_query_language(masked_query)

        # --------------------------------------------------------------------
        # 3. ROUTE
        # --------------------------------------------------------------------
        state = AgentState.ROUTE
        t_route = time.monotonic()
        route_res = await self.router.route(masked_query)
        assistant_metrics.observe_stage_latency("route", time.monotonic() - t_route)

        if route_res.route == RouteClass.UNCLEAR:
            assistant_metrics.inc(
                "pfa_assistant_requests_total",
                route="unclear",
                status="clarification_needed",
                lang=lang,
            )
            return AssistantChatResponse(
                status="clarification_needed",
                answer=route_res.clarifying_question or "Could you clarify your question?",
                language=lang,
                route=RouteClass.UNCLEAR,
                confidence=route_res.confidence,
                clarifying_question=route_res.clarifying_question,
                trace_id=trace_id,
                prompt_version=prompt_version,
            )

        if route_res.route == RouteClass.OUT_OF_SCOPE:
            assistant_metrics.inc("pfa_assistant_requests_total", route="out_of_scope", status="refusal", lang=lang)
            return AssistantChatResponse(
                status="refusal",
                answer=route_res.clarifying_question or "This request is outside the scope of this assistant.",
                language=lang,
                route=RouteClass.OUT_OF_SCOPE,
                confidence=route_res.confidence,
                trace_id=trace_id,
                prompt_version=prompt_version,
            )

        # --------------------------------------------------------------------
        # 4. PLAN
        # --------------------------------------------------------------------
        state = AgentState.PLAN
        planner_fallback = False
        planner_fallback_reason: str | None = None
        plan_res = await self.planner.plan(
            masked_query,
            user_id=str(user.id),
            default_route=route_res.route,
        )
        plan = plan_res.plan
        planner_fallback = plan_res.fallback_used
        planner_fallback_reason = plan_res.fallback_reason
        if planner_fallback:
            degraded = True

        # --------------------------------------------------------------------
        # 5. EXECUTE_TOOLS and/or RETRIEVE
        # --------------------------------------------------------------------
        state = AgentState.EXECUTE_TOOLS
        facts: list[Fact] = []
        step_records: list[StepExecutionRecord] = []
        budget = ToolExecutionBudget(max_tool_calls=4, max_total_rows=500, overall_budget_seconds=10.0)
        tool_ctx = ToolContext(
            user_id=user.id,
            request_id=trace_id,
            session=self.session,
        )

        t_tools = time.monotonic()
        for idx, call in enumerate(plan.tool_calls, 1):
            t_step_start = time.monotonic()
            step_status = "success"
            step_error: str | None = None
            try:
                tools_called.append(call.tool_name)
                res = await self.executor.execute(call.tool_name, call.arguments, tool_ctx, budget=budget)
                if res.ok:
                    facts.extend(res.facts)
                else:
                    step_status = "error"
                    step_error = "; ".join(res.warnings) if res.warnings else "tool_execution_failed"
                    degraded = True
            except ToolError as te:
                step_status = "tool_error"
                step_error = str(te)
                degraded = True
            except Exception as e:
                step_status = "exception"
                step_error = type(e).__name__
                degraded = True
            finally:
                step_dur = round((time.monotonic() - t_step_start) * 1000, 2)
                step_records.append(
                    StepExecutionRecord(
                        step_index=idx,
                        tool_name=call.tool_name,
                        arguments_summary=summarize_arguments(call.tool_name, call.arguments),
                        duration_ms=step_dur,
                        status=step_status,
                        error=step_error,
                    )
                )
        assistant_metrics.observe_stage_latency("tools", time.monotonic() - t_tools)

        evidence_chunks: list[dict[str, Any]] = []
        alias_to_chunk_meta: dict[str, dict[str, Any]] = {}

        if plan.needs_retrieval and plan.retrieval_query:
            state = AgentState.RETRIEVE
            t_ret = time.monotonic()
            try:
                ret_results = await self.retriever.retrieve(plan.retrieval_query)
                for idx, r in enumerate(ret_results.chunks, 1):
                    alias = f"E{idx}"
                    alias_to_chunk_meta[alias] = {
                        "chunk_id": str(r.chunk_id),
                        "document_title": r.title,
                        "publisher": r.publisher,
                        "heading": r.heading_path,
                        "source_url": r.source_url,
                        "effective_date": r.effective_date,
                    }
                    evidence_chunks.append({
                        "alias": alias,
                        "chunk_id": str(r.chunk_id),
                        "title": r.title,
                        "content": r.text,
                        "source_url": r.source_url,
                    })
            except Exception:
                degraded = True
            finally:
                assistant_metrics.observe_stage_latency("retrieval", time.monotonic() - t_ret)

        # --------------------------------------------------------------------
        # 6. COMPOSE
        # --------------------------------------------------------------------
        state = AgentState.COMPOSE
        t_comp = time.monotonic()
        disclaimer = None
        if route_res.route == RouteClass.CREDIT_READINESS:
            disclaimer = (
                "Indicative readiness assessment only. This is not a loan approval, "
                "rejection, or numerical credit score."
            )

        composed_answer = ""
        cited_aliases: list[str] = []
        facts_used: list[str] = [f.id for f in facts]

        try:
            composer_out = await self.composer.compose(
                question=masked_query,
                route=route_res.route,
                facts=facts,
                evidence_chunks=evidence_chunks,
                disclaimer=disclaimer,
            )
            composed_answer = composer_out.answer
            cited_aliases = composer_out.cited_aliases
            if composer_out.facts_used:
                facts_used = composer_out.facts_used
        except Exception:
            degraded = True
            composed_answer = build_structured_fallback(
                route=route_res.route,
                facts=facts,
                evidence_chunks=evidence_chunks,
                language=lang,
            )
        finally:
            assistant_metrics.observe_stage_latency("compose", time.monotonic() - t_comp)

        # --------------------------------------------------------------------
        # 7. VALIDATE_ANSWER (Numeric Grounding + Citations + Contacts)
        # --------------------------------------------------------------------
        state = AgentState.VALIDATE_ANSWER
        if not degraded and composed_answer:
            # 1. Numeric Grounding Check
            grounding_res = self.grounding_validator.validate(
                composed_answer,
                facts=facts,
                evidence_chunks=evidence_chunks,
            )
            validation_outcomes["numeric_grounding"] = grounding_res.is_valid

            # 2. Content & Citation Policy Check
            content_violations = []
            for pattern, reason in self.answer_validator.POLICY_VIOLATION_PATTERNS:
                if pattern.search(composed_answer):
                    content_violations.append(f"PolicyViolation: {reason}")
            for cited in re.findall(r"\[(E\d+)\]", composed_answer):
                if cited not in alias_to_chunk_meta:
                    content_violations.append(
                        f"InvalidCitationAlias: Cited alias '{cited}' was not in retrieved evidence"
                    )
            content_valid = len(content_violations) == 0
            validation_outcomes["content_policy"] = content_valid

            if not grounding_res.is_valid or not content_valid:
                # Attempt ONE bounded repair
                feedback_items = []
                if not grounding_res.is_valid:
                    feedback_items.append(f"Ungrounded numbers detected: {grounding_res.ungrounded_numbers}")
                if not content_valid:
                    feedback_items.append(f"Policy violations: {content_violations}")

                try:
                    repaired_out = await self.composer.compose(
                        question=masked_query,
                        route=route_res.route,
                        facts=facts,
                        evidence_chunks=evidence_chunks,
                        disclaimer=disclaimer,
                        feedback="; ".join(feedback_items),
                    )
                    re_grounding = self.grounding_validator.validate(
                        repaired_out.answer,
                        facts=facts,
                        evidence_chunks=evidence_chunks,
                    )
                    re_violations = []
                    for pattern, reason in self.answer_validator.POLICY_VIOLATION_PATTERNS:
                        if pattern.search(repaired_out.answer):
                            re_violations.append(f"PolicyViolation: {reason}")
                    for cited in re.findall(r"\[(E\d+)\]", repaired_out.answer):
                        if cited not in alias_to_chunk_meta:
                            re_violations.append(
                                f"InvalidCitationAlias: Cited alias '{cited}' was not in retrieved evidence"
                            )
                    re_content = len(re_violations) == 0

                    if re_grounding.is_valid and re_content:
                        composed_answer = repaired_out.answer
                        cited_aliases = repaired_out.cited_aliases
                    else:
                        # Fallback to structured extractive answer directly from facts
                        degraded = True
                        composed_answer = build_structured_fallback(
                            route=route_res.route,
                            facts=facts,
                            evidence_chunks=evidence_chunks,
                            language=lang,
                        )
                except Exception:
                    degraded = True
                    composed_answer = build_structured_fallback(
                        route=route_res.route,
                        facts=facts,
                        evidence_chunks=evidence_chunks,
                        language=lang,
                    )

        # Map citation aliases to real validated document metadata
        final_citations: list[Citation] = []
        all_cited_aliases = list(dict.fromkeys(cited_aliases + re.findall(r"\[(E\d+)\]", composed_answer)))
        for alias in all_cited_aliases:
            meta = alias_to_chunk_meta.get(alias)
            if meta:
                final_citations.append(
                    Citation(
                        alias=alias,
                        chunk_id=meta["chunk_id"],
                        document_title=meta["document_title"],
                        publisher=meta["publisher"],
                        heading=meta["heading"],
                        source_url=meta["source_url"],
                        effective_date=meta["effective_date"],
                    )
                )

        # --------------------------------------------------------------------
        # 8. RESPOND + AUDIT ENTRY (Metadata only, never sensitive text)
        # --------------------------------------------------------------------
        state = AgentState.RESPOND
        logger.debug("Orchestrator completed in state: %s", state.value)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Record Agent Trace (No raw text or amounts)
        trace_record = AgentTrace(
            trace_id=str(trace_id),
            run_id=str(uuid.uuid4()),
            user_id=str(user.id),
            created_at=time.time(),
            status="success" if not degraded else "degraded_fallback",
            fallback_used=planner_fallback or degraded,
            fallback_reason=planner_fallback_reason if planner_fallback else None,
            steps=step_records,
            duration_ms=float(latency_ms),
            validation_results={k: bool(v) for k, v in validation_outcomes.items()},
        )
        record_agent_trace(trace_record)

        # Persist conversation message if conversation_id was provided (masked text only)
        if getattr(request, "conversation_id", None):
            try:
                user_msg = Message(
                    conversation_id=request.conversation_id,
                    user_id=user.id,
                    role=MessageRole.USER,
                    content_masked=masked_query,
                    trace_id=str(trace_id),
                )
                assistant_msg = Message(
                    conversation_id=request.conversation_id,
                    user_id=user.id,
                    role=MessageRole.ASSISTANT,
                    content_masked=composed_answer,
                    tool_calls=[r.model_dump() for r in step_records] if step_records else None,
                    trace_id=str(trace_id),
                )
                self.session.add(user_msg)
                self.session.add(assistant_msg)
                if isinstance(self.session, AsyncSession):
                    await self.session.flush()
                else:
                    self.session.flush()
            except Exception as e:
                logger.warning("Conversation message persistence failed: %s", e)

        # Save audit entry metadata
        try:
            audit = AuditTrail(
                actor=AuditActor.USER,
                user_id=user.id,
                action="agent_trace",
                resource_type="agent_trace",
                resource_id=str(trace_id),
                metadata_json=trace_record.model_dump(),
            )
            self.session.add(audit)
            if isinstance(self.session, AsyncSession):
                await self.session.flush()
            else:
                self.session.flush()
        except Exception:
            pass

        resp_status = "success" if not degraded else "degraded_fallback"
        final_confidence = "low" if degraded else route_res.confidence
        if degraded and (not facts and not evidence_chunks):
            if route_res.route == RouteClass.PROTECT:
                composed_answer = build_structured_fallback(
                    route=RouteClass.PROTECT,
                    facts=facts,
                    evidence_chunks=evidence_chunks,
                    language=lang,
                )
            else:
                composed_answer = "The service is temporarily unavailable. Please try again shortly."

        assistant_metrics.inc(
            "pfa_assistant_requests_total",
            route=route_res.route.value,
            status=resp_status,
            lang=lang,
        )
        if degraded:
            assistant_metrics.inc("pfa_assistant_fallbacks_total", reason="degraded")

        return AssistantChatResponse(
            status="success" if not degraded else "degraded_fallback",
            answer=composed_answer,
            language=lang,
            citations=final_citations,
            facts_used=facts_used,
            route=route_res.route,
            confidence=final_confidence,
            degraded=degraded,
            disclaimer=disclaimer,
            trace_id=trace_id,
            prompt_version=prompt_version,
        )

    def _create_plan(self, route: RouteClass, query: str) -> OrchestratorPlan:
        q_lower = query.lower()
        today = date.today()
        # Default date range: current month or last 30 days
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
                        arguments={"start_date": str(start_date), "end_date": str(end_date), "granularity": "monthly"},
                    )
                )
            else:
                tool_calls.append(
                    ToolCallSpec(
                        tool_name="get_spending_summary",
                        arguments={"start_date": str(start_date), "end_date": str(end_date)},
                    )
                )

        elif route == RouteClass.CREDIT_READINESS:
            tool_calls.append(ToolCallSpec(tool_name="get_borrow_readiness", arguments={"refresh": False}))

        elif route == RouteClass.PROTECT:
            needs_retrieval = True
            retrieval_query = query

        elif route == RouteClass.KNOWLEDGE:
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
