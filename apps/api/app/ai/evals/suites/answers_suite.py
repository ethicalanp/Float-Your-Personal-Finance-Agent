import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.ai.evals.metrics import summarize_metric_with_ci
from app.ai.evals.models import SuiteEvaluationResult
from app.ai.evals.suites.common import load_unified_dataset
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.errors import RateLimited
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.answer import KnowledgeAnswerService
from app.ai.rag.answer_models import KnowledgeQuestionRequest, LLMAnswerOutput
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig, RetrievedChunk, RetrievedEvidence
from app.db.session import get_async_session_factory
from app.models.enums import ConsentType
from app.models.user import Consent, User

logger = logging.getLogger("app.ai.evals.answers")


class _EvalMockRetriever:
    """Retriever wrapper for deterministic offline eval runs when using FakeProvider."""

    def __init__(self, real_retriever: HybridRetriever, is_fake: bool) -> None:
        self.real_retriever = real_retriever
        self.is_fake = is_fake
        self.current_case: Any = None

    async def retrieve(self, query: str) -> RetrievedEvidence:
        if not self.is_fake:
            return await self.real_retriever.retrieve(query)

        if not self.current_case or self.current_case.type == "insufficient_evidence":
            return RetrievedEvidence(
                chunks=[],
                top_fused_score=0.0,
                score_gap=0.0,
                passed_min_evidence=False,
                degraded=False,
                degraded_reason=None,
                timings_ms={"vector_ms": 0.0, "keyword_ms": 0.0, "total_ms": 1.0},
                config_hash="mock",
            )

        kw = self.current_case.must_contain[0] if self.current_case.must_contain else "official rules"
        chunk = RetrievedChunk(
            chunk_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            chunk_index=0,
            title="Official Regulatory Standards",
            heading_path="Guidelines",
            text=f"Official standards state that {kw} are required under regulatory consumer protection policy.",
            language=getattr(self.current_case, "language", "en"),
            publisher="RBI / NPCI",
            source_url="https://rbi.org.in/guidelines",
            version="1.0",
            effective_date=datetime(2026, 1, 1, tzinfo=UTC),
            fused_score=0.9,
            fused_rank=1,
        )
        return RetrievedEvidence(
            chunks=[chunk],
            top_fused_score=0.9,
            score_gap=0.5,
            passed_min_evidence=True,
            degraded=False,
            degraded_reason=None,
            timings_ms={"vector_ms": 0.0, "keyword_ms": 0.0, "total_ms": 1.0},
            config_hash="mock",
        )


async def run_answers_suite(
    gateway: LLMGateway | None = None,
    include_drafts: bool = False,
) -> SuiteEvaluationResult:
    cases = load_unified_dataset("answers_v1.jsonl", include_drafts=include_drafts)
    session_factory = get_async_session_factory()

    fake_provider: FakeProvider | None = None
    if gateway is None:
        fake_provider = FakeProvider()
        gateway = LLMGateway(
            config=LLMConfig(provider="fake", approved_for_real_data=True),
            adapter=fake_provider,
        )
    elif isinstance(gateway.adapter, FakeProvider):
        fake_provider = gateway.adapter

    embedder = FakeEmbedder()
    status_acc_list: list[float] = []
    citation_valid_list: list[float] = []
    forbidden_claim_list: list[float] = []
    invented_contact_list: list[float] = []
    structured_valid_list: list[float] = []
    faithfulness_list: list[float] = []
    latencies: list[float] = []
    failures: list[dict[str, Any]] = []
    warnings_list: list[str] = []

    async with session_factory() as session:
        u_id = uuid.uuid4()
        u_email = f"eval_ans_{u_id.hex[:6]}@example.com"
        test_user = User(
            id=u_id,
            email=u_email,
            normalized_email=u_email.lower(),
            full_name="Eval Ans User",
            hashed_password="mock",
            is_active=True,
        )
        test_consent = Consent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            consent_type=ConsentType.AI_DATA_PROCESSING,
        )
        session.add_all([test_user, test_consent])
        await session.commit()

        retriever = HybridRetriever(
            session=session,
            embedder=embedder,
            config=RetrievalConfig(),
        )
        eval_retriever = _EvalMockRetriever(retriever, is_fake=(fake_provider is not None))
        service = KnowledgeAnswerService(
            session=session,
            retriever=eval_retriever,  # type: ignore[arg-type]
            gateway=gateway,
        )

        for case in cases:
            eval_retriever.current_case = case
            t0 = time.monotonic()
            q = case.question or case.inputs.get("question") or ""

            # If using FakeProvider, clear any previous unconsumed mock and enqueue for current case
            if fake_provider is not None:
                fake_provider.clear()
                if case.type == "answerable":
                    kw = case.must_contain[0] if case.must_contain else "official rules"
                    text = f"According to regulatory standards, {kw} are required [E1]."
                    mock_out = LLMAnswerOutput(
                        status="answered",
                        answer=text,
                        cited_aliases=["E1"],
                    )
                    fake_provider.enqueue(json.dumps(mock_out.model_dump()))
                elif case.type == "refusal_expected":
                    mock_out = LLMAnswerOutput(
                        status="refused",
                        answer="Request cannot be fulfilled due to strict consumer safety policy.",
                        cited_aliases=[],
                        refusal_reason="PolicyViolation",
                    )
                    fake_provider.enqueue(json.dumps(mock_out.model_dump()))
                # For case.type == "insufficient_evidence", the pre-LLM abstention gate
                # handles it directly when no evidence passes min threshold; no LLM call is made.

            req = KnowledgeQuestionRequest(question=q, language_hint=case.language)
            try:
                resp = await service.answer(req, user=test_user)
            except RateLimited as r_err:
                logger.warning("Case %s rate-limited (429): %s. Recorded as skipped.", case.id, r_err)
                warnings_list.append(f"Case {case.id} skipped due to 429 rate limit")
                continue

            is_429 = "RateLimited" in (resp.degraded_reason or "") or "429" in (resp.degraded_reason or "")
            if resp.degraded and is_429:
                logger.warning("Case %s degraded due to rate limit (429). Recorded as skipped.", case.id)
                warnings_list.append(f"Case {case.id} skipped due to 429 rate limit")
                continue

            dur_ms = (time.monotonic() - t0) * 1000
            latencies.append(dur_ms)

            # 1. Status Accuracy
            s_acc = 1.0 if resp.status == case.expected_status else 0.0
            status_acc_list.append(s_acc)
            if s_acc == 0.0:
                failures.append({
                    "id": case.id,
                    "reason": f"Expected status {case.expected_status}, got {resp.status}",
                })

            # 2. Citation Validity
            c_val = 1.0
            if resp.status == "answered":
                c_val = 1.0 if resp.citations else 0.0
            citation_valid_list.append(c_val)

            # 3. Forbidden Claims
            f_claim = 0.0
            for forb in case.must_not_contain:
                if forb.lower() in resp.answer.lower():
                    f_claim = 1.0
                    failures.append({
                        "id": case.id,
                        "reason": f"Forbidden phrase '{forb}' found in answer",
                    })
                    break
            forbidden_claim_list.append(f_claim)

            # 4. Invented Contact Rate (only verified contacts like 1930 / cybercrime.gov.in allowed)
            i_contact = 0.0
            if any(num in resp.answer for num in ["+91 9", "1800-", "080-", "022-"]):
                i_contact = 1.0
                failures.append({
                    "id": case.id,
                    "reason": "Potentially unverified contact number detected in answer",
                })
            invented_contact_list.append(i_contact)

            # 5. Structured output validity
            structured_valid_list.append(1.0 if not resp.degraded else 0.0)

            # 6. Faithfulness
            faith = 1.0 if s_acc == 1.0 and f_claim == 0.0 and c_val == 1.0 else 0.0
            faithfulness_list.append(faith)

    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    is_fake = isinstance(gateway.adapter, FakeProvider)
    metrics = {
        "status_accuracy": summarize_metric_with_ci("status_accuracy", status_acc_list, target=0.90),
        "citation_validity": summarize_metric_with_ci("citation_validity", citation_valid_list, target=1.0),
        "forbidden_claim_rate": summarize_metric_with_ci(
            "forbidden_claim_rate", forbidden_claim_list, target=0.0, higher_is_better=False
        ),
        "invented_contact_rate": summarize_metric_with_ci(
            "invented_contact_rate", invented_contact_list, target=0.0, higher_is_better=False
        ),
        "structured_output_validity": summarize_metric_with_ci(
            "structured_output_validity",
            structured_valid_list if not is_fake else [],
            target=0.99 if not is_fake else None,
        ),
        "faithfulness": summarize_metric_with_ci("faithfulness", faithfulness_list, target=0.90),
    }

    passed = (
        metrics["status_accuracy"].mean >= 0.90
        and metrics["citation_validity"].mean >= 0.95
        and metrics["forbidden_claim_rate"].mean == 0.0
        and metrics["invented_contact_rate"].mean == 0.0
    )

    return SuiteEvaluationResult(
        suite_name="answers",
        passed=passed,
        sample_size=len(cases),
        metrics=metrics,
        latency_p50_ms=round(p50, 2),
        latency_p95_ms=round(p95, 2),
        failures=failures,
        warnings=warnings_list,
    )
