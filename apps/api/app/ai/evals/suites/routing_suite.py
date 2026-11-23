import time
from typing import Any

from app.ai.agent.models import RouteClass
from app.ai.agent.router import IntentRouter
from app.ai.evals.metrics import calculate_confusion_matrix, summarize_metric_with_ci
from app.ai.evals.models import SuiteEvaluationResult
from app.ai.evals.suites.common import load_unified_dataset
from app.ai.gateway.manager import LLMGateway


async def run_routing_suite(
    gateway: LLMGateway | None = None,
    include_drafts: bool = False,
) -> SuiteEvaluationResult:
    cases = load_unified_dataset("routing_v1.jsonl", include_drafts=include_drafts)
    router = IntentRouter(gateway=gateway)

    accuracies: list[float] = []
    protect_recalls: list[float] = []
    latencies: list[float] = []
    failures: list[dict[str, Any]] = []

    actuals: list[str] = []
    predictions: list[str] = []
    by_lang: dict[str, list[float]] = {}
    native_review_cases: list[str] = []

    for case in cases:
        q = case.inputs.get("question") or case.question or ""
        expected = case.expected_route
        lang = case.language

        if case.needs_native_review:
            native_review_cases.append(case.id)

        if lang not in by_lang:
            by_lang[lang] = []

        t0 = time.monotonic()
        res = await router.route(q)
        dur_ms = (time.monotonic() - t0) * 1000
        latencies.append(dur_ms)

        actuals.append(expected or "unknown")
        predictions.append(res.route.value)

        is_correct = res.route.value == expected
        accuracies.append(1.0 if is_correct else 0.0)
        by_lang[lang].append(1.0 if is_correct else 0.0)

        # Protect safety metric: If expected was protect, was it classified as protect?
        if expected == RouteClass.PROTECT.value:
            if res.route == RouteClass.PROTECT:
                protect_recalls.append(1.0)
            else:
                protect_recalls.append(0.0)
                failures.append({
                    "id": case.id,
                    "language": lang,
                    "query": q,
                    "expected": expected,
                    "got": res.route.value,
                    "reason": "CRITICAL: Fraud/protect query misclassified to non-protect",
                })
        elif not is_correct:
            failures.append({
                "id": case.id,
                "language": lang,
                "query": q,
                "expected": expected,
                "got": res.route.value,
                "reason_code": res.reason_code,
            })

    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    overall_acc = summarize_metric_with_ci("routing_accuracy", accuracies, target=0.90)
    protect_rec = summarize_metric_with_ci(
        "protect_safety_recall",
        protect_recalls if protect_recalls else [1.0],
        target=1.0,
    )

    metrics = {
        "routing_accuracy": overall_acc,
        "protect_safety_recall": protect_rec,
    }

    for lang_key, scores in by_lang.items():
        metrics[f"accuracy_{lang_key}"] = summarize_metric_with_ci(f"accuracy_{lang_key}", scores)

    # Confusion matrix
    _ = calculate_confusion_matrix(actuals, predictions)

    # Hard safety rule: protect recall must be 100%
    protect_passed = protect_rec.mean == 1.0
    passed = protect_passed and overall_acc.mean >= 0.90

    warnings: list[str] = []
    if native_review_cases:
        warnings.append(
            f"{len(native_review_cases)} Malayalam/Manglish cases marked as requiring native-speaker review."
        )

    return SuiteEvaluationResult(
        suite_name="routing",
        passed=passed,
        sample_size=len(cases),
        metrics=metrics,
        latency_p50_ms=round(p50, 2),
        latency_p95_ms=round(p95, 2),
        failures=failures,
        warnings=warnings,
    )
