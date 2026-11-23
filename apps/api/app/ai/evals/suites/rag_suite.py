from app.ai.evals.metrics import summarize_metric_with_ci
from app.ai.evals.models import SuiteEvaluationResult
from app.ai.evals.runner import evaluate_configuration, load_dataset
from app.ai.evals.suites.common import find_dataset_path
from app.ai.rag.dependencies import get_embedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.db.session import get_async_session_factory


async def run_rag_suite(
    retriever: HybridRetriever | None = None,
    split: str | None = None,
) -> SuiteEvaluationResult:
    dataset_path = find_dataset_path("rag_v1.jsonl")
    cases = load_dataset(dataset_path, split=split)

    if retriever is None:
        try:
            embedder = get_embedder()
        except Exception:
            embedder = FakeEmbedder()
        session_factory = get_async_session_factory()
        session = session_factory()
        retriever = HybridRetriever(
            session=session,
            embedder=embedder,
            config=RetrievalConfig(),
        )

    overall, by_lang, by_type, worst, abstention, (r5_list, r10_list, mrr_list, ndcg5_list, hr_list) = (
        await evaluate_configuration(
            retriever,
            cases,
        )
    )

    metrics = {
        "recall_at_5": summarize_metric_with_ci(
            "recall_at_5",
            r5_list,
            target=0.85,
        ),
        "recall_at_10": summarize_metric_with_ci(
            "recall_at_10",
            r10_list,
        ),
        "mrr": summarize_metric_with_ci(
            "mrr",
            mrr_list,
        ),
        "ndcg_at_5": summarize_metric_with_ci(
            "ndcg_at_5",
            ndcg5_list,
        ),
        "hit_rate": summarize_metric_with_ci(
            "hit_rate",
            hr_list,
        ),
    }

    # Target: Recall@5 >= 85%
    passed = overall.recall_at_5.mean >= 0.85

    return SuiteEvaluationResult(
        suite_name="rag",
        passed=passed,
        sample_size=len(cases),
        metrics=metrics,
        latency_p50_ms=overall.latency_p50_ms,
        latency_p95_ms=overall.latency_p95_ms,
        failures=worst[:10],
    )
