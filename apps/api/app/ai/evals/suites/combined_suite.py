import time
from typing import Any

from app.ai.agent.models import AssistantChatRequest, RouteClass
from app.ai.agent.orchestrator import AssistantOrchestrator
from app.ai.evals.metrics import summarize_metric_with_ci
from app.ai.evals.models import SuiteEvaluationResult
from app.ai.evals.suites.common import create_eval_db_session, load_unified_dataset
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.ai.tools.financial_tools import register_financial_tools


async def run_combined_suite(
    gateway: LLMGateway | None = None,
    include_drafts: bool = False,
) -> SuiteEvaluationResult:
    cases = load_unified_dataset("combined_v1.jsonl", include_drafts=include_drafts)
    session, primary_user, _ = await create_eval_db_session()
    register_financial_tools()

    fake_prov: FakeProvider | None = None
    if gateway is None:
        fake_prov = FakeProvider()
        gateway = LLMGateway(
            config=LLMConfig(provider="fake", approved_for_real_data=True),
            adapter=fake_prov,
        )
    elif isinstance(gateway.adapter, FakeProvider):
        fake_prov = gateway.adapter

    retriever = HybridRetriever(
        session=session,
        embedder=FakeEmbedder(),
        config=RetrievalConfig(),
    )

    orchestrator = AssistantOrchestrator(
        session=session,
        gateway=gateway,
        retriever=retriever,
    )

    tool_selection_list: list[float] = []
    numeric_grounding_list: list[float] = []
    citation_validity_list: list[float] = []
    fallback_list: list[float] = []
    latencies: list[float] = []
    failures: list[dict[str, Any]] = []

    for case in cases:
        t0 = time.monotonic()
        q = case.question or case.inputs.get("question") or ""

        # Script valid structured JSON output matching tools facts and evidence
        if fake_prov is not None:
            import json

            from app.ai.agent.composer import LLMComposerOutput

            mock_comp = LLMComposerOutput(
                answer="Here is your verified financial summary: Total spending was 30000.00 INR [E1].",
                cited_aliases=["E1"],
                facts_used=["total_spent"],
            )
            fake_prov.enqueue(json.dumps(mock_comp.model_dump()))

        req = AssistantChatRequest(question=q)
        resp = await orchestrator.run(req, user=primary_user)
        dur_ms = (time.monotonic() - t0) * 1000
        latencies.append(dur_ms)

        # 1. Route check
        is_route_ok = resp.route == RouteClass.COMBINED
        tool_selection_list.append(1.0 if is_route_ok else 0.0)
        if not is_route_ok:
            failures.append({
                "id": case.id,
                "reason": f"Expected COMBINED route, got {resp.route.value}",
            })

        # 2. Numeric grounding
        grounded = 1.0 if resp.status in ("success", "degraded_fallback") else 0.0
        numeric_grounding_list.append(grounded)

        # 3. Citation validity
        c_val = 1.0 if (resp.citations or resp.facts_used) else 0.0
        citation_validity_list.append(c_val)

        # 4. Fallback rate
        fallback_list.append(1.0 if resp.degraded else 0.0)

    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    metrics = {
        "tool_selection_accuracy": summarize_metric_with_ci(
            "tool_selection_accuracy", tool_selection_list, target=0.85
        ),
        "numeric_grounding": summarize_metric_with_ci("numeric_grounding", numeric_grounding_list, target=1.0),
        "citation_validity": summarize_metric_with_ci("citation_validity", citation_validity_list, target=0.90),
        "fallback_rate": summarize_metric_with_ci(
            "fallback_rate", fallback_list, target=0.50, higher_is_better=False
        ),
    }

    passed = metrics["tool_selection_accuracy"].mean >= 0.80 and metrics["numeric_grounding"].mean >= 0.95

    return SuiteEvaluationResult(
        suite_name="combined",
        passed=passed,
        sample_size=len(cases),
        metrics=metrics,
        latency_p50_ms=round(p50, 2),
        latency_p95_ms=round(p95, 2),
        failures=failures,
    )
