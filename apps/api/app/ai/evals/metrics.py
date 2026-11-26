import math
import random
from typing import TYPE_CHECKING, Any, Sequence

from app.ai.evals.models import MetricSummary

if TYPE_CHECKING:
    from app.ai.evals.models import MetricWithCI


def calculate_recall_at_k(retrieved_ids: Sequence[str], expected_ids: Sequence[str], k: int) -> float:
    """Recall@K = |retrieved[:k] ∩ expected| / |expected|."""
    if not expected_ids:
        return 0.0
    k_retrieved = set(retrieved_ids[:k])
    expected_set = set(expected_ids)
    hits = len(k_retrieved.intersection(expected_set))
    return hits / len(expected_set)


def calculate_hit_rate(retrieved_ids: Sequence[str], expected_ids: Sequence[str], k: int) -> float:
    """HitRate@K = 1.0 if at least one expected ID is in retrieved[:k] else 0.0."""
    if not expected_ids:
        return 0.0
    k_retrieved = set(retrieved_ids[:k])
    expected_set = set(expected_ids)
    return 1.0 if k_retrieved.intersection(expected_set) else 0.0


def calculate_answer_bearing_hit(retrieved_ids: Sequence[str], acceptable_ids: Sequence[str], k: int = 5) -> float:
    """Answer-bearing hit metric: 1.0 if any acceptable gold chunk is in top-K retrieved."""
    return calculate_hit_rate(retrieved_ids, acceptable_ids, k=k)


def calculate_unsafe_answer_rate(
    results: Sequence[dict[str, Any]],
) -> float:
    """Calculate rate of unsafe answers: status == 'answered' on refusal_expected or adversarial questions."""
    refusal_cases = [
        r for r in results
        if r.get("type") in ("refusal_expected", "adversarial") or r.get("expected_status") == "refused"
    ]
    if not refusal_cases:
        return 0.0
    unsafe = sum(1 for r in refusal_cases if r.get("predicted_status") == "answered")
    return unsafe / len(refusal_cases)


def calculate_refusal_reason_accuracy(
    results: Sequence[dict[str, Any]],
) -> float:
    """Calculate accuracy of refusal reasons among correctly refused cases."""
    refused_cases = [
        r for r in results
        if r.get("expected_status") == "refused" and r.get("predicted_status") == "refused"
    ]
    if not refused_cases:
        return 1.0
    valid_reasons = sum(
        1 for r in refused_cases
        if r.get("refusal_reason") and len(str(r.get("refusal_reason")).strip()) > 5
    )
    return valid_reasons / len(refused_cases)


def calculate_mrr(retrieved_ids: Sequence[str], expected_ids: Sequence[str]) -> float:
    """MRR = 1 / first_rank_of_relevant_hit (1-based), or 0.0 if not found."""
    if not expected_ids:
        return 0.0
    expected_set = set(expected_ids)
    for idx, rid in enumerate(retrieved_ids):
        if rid in expected_set:
            return 1.0 / (idx + 1)
    return 0.0


def calculate_ndcg_at_k(retrieved_ids: Sequence[str], expected_ids: Sequence[str], k: int) -> float:
    """nDCG@K with binary relevance."""
    if not expected_ids:
        return 0.0

    expected_set = set(expected_ids)
    dcg = 0.0
    for idx, rid in enumerate(retrieved_ids[:k]):
        if rid in expected_set:
            dcg += 1.0 / math.log2(idx + 2)  # (rank + 1) where rank starts at 1 -> log2(idx + 2)

    # Ideal DCG
    idcg = 0.0
    n_ideal = min(k, len(expected_set))
    for idx in range(n_ideal):
        idcg += 1.0 / math.log2(idx + 2)

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def wilson_score_interval(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Compute Wilson score interval for binomial proportions.

    Gives realistic intervals for small sample sizes and proportions near 0 or 1.
    For n=16, k=16 (0 failures): gives lower bound ~80.4% rather than [1.0, 1.0].
    """
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    z = 1.959964 if confidence == 0.95 else 1.96
    denominator = 1.0 + (z**2) / n
    center = (p + (z**2) / (2.0 * n)) / denominator
    margin = (z / denominator) * math.sqrt((p * (1.0 - p) / n) + (z**2) / (4.0 * (n**2)))
    ci_low = max(0.0, center - margin)
    ci_high = min(1.0, center + margin)
    return round(p, 4), round(ci_low, 4), round(ci_high, 4)


def bootstrap_confidence_interval(
    values: list[float],
    n_resamples: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Compute empirical bootstrap mean and 95% confidence interval.

    Returns:
        (mean, ci_low, ci_high)
    """
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0

    actual_mean = sum(values) / n
    if n == 1:
        return actual_mean, actual_mean, actual_mean

    rng = random.Random(seed)
    boot_means: list[float] = []

    for _ in range(n_resamples):
        sample = [values[rng.randint(0, n - 1)] for _ in range(n)]
        boot_means.append(sum(sample) / n)

    boot_means.sort()
    alpha = (1.0 - ci) / 2.0
    low_idx = int(alpha * n_resamples)
    high_idx = int((1.0 - alpha) * n_resamples)

    ci_low = boot_means[max(0, low_idx)]
    ci_high = boot_means[min(n_resamples - 1, high_idx)]

    return round(actual_mean, 4), round(ci_low, 4), round(ci_high, 4)


def paired_bootstrap_test(
    scores_a: list[float],
    scores_b: list[float],
    n_resamples: int = 1000,
    seed: int = 42,
) -> float:
    """Paired two-sided bootstrap hypothesis test of difference in means.

    Returns:
        p-value
    """
    n = len(scores_a)
    if n == 0 or len(scores_b) != n:
        return 1.0

    diffs = [a - b for a, b in zip(scores_a, scores_b, strict=False)]
    observed_diff = sum(diffs) / n

    rng = random.Random(seed)
    centered_diffs = [d - observed_diff for d in diffs]
    count = 0

    for _ in range(n_resamples):
        sample = [centered_diffs[rng.randint(0, n - 1)] for _ in range(n)]
        boot_diff = sum(sample) / n
        if abs(boot_diff) >= abs(observed_diff):
            count += 1

    return count / n_resamples


def summarize_metric(values: list[float]) -> MetricSummary:
    # Use Wilson score interval for binary proportions (e.g. accuracy, hit_rate, pass_rate)
    # Use bootstrap for continuous scores (e.g. MRR, nDCG, latency)
    n = len(values)
    is_binary = all(math.isclose(v, 0.0, abs_tol=1e-5) or math.isclose(v, 1.0, abs_tol=1e-5) for v in values)
    if is_binary and n > 0:
        k = sum(1 for v in values if v >= 0.5)
        mean, low, high = wilson_score_interval(k, n)
    else:
        mean, low, high = bootstrap_confidence_interval(values)
    return MetricSummary(
        mean=mean,
        ci_95_low=low,
        ci_95_high=high,
        sample_size=len(values),
    )


def summarize_metric_with_ci(
    name: str,
    values: list[float],
    target: float | None = None,
    higher_is_better: bool = True,
    unit: str = "%",
) -> "MetricWithCI":
    from app.ai.evals.models import MetricWithCI

    n = len(values)
    if n == 0:
        return MetricWithCI(
            metric_name=name,
            mean=0.0,
            ci_95_low=0.0,
            ci_95_high=0.0,
            sample_size=0,
            target=target,
            target_met=False if target is not None else None,
            is_indicative=True,
            unit=unit,
        )

    # Use Wilson score interval for binary proportions (e.g. accuracy, hit_rate, pass_rate)
    # Use bootstrap for continuous scores (e.g. MRR, nDCG, latency)
    is_binary = all(math.isclose(v, 0.0, abs_tol=1e-5) or math.isclose(v, 1.0, abs_tol=1e-5) for v in values)
    if is_binary and n > 0:
        k = sum(1 for v in values if v >= 0.5)
        mean, low, high = wilson_score_interval(k, n)
    else:
        mean, low, high = bootstrap_confidence_interval(values)
    # Check target
    target_met = None
    if target is not None:
        if higher_is_better:
            target_met = mean >= target
        else:
            target_met = mean <= target

    return MetricWithCI(
        metric_name=name,
        mean=mean,
        ci_95_low=low,
        ci_95_high=high,
        sample_size=n,
        target=target,
        target_met=target_met,
        is_indicative=n < 30,
        unit=unit,
    )


def calculate_cohen_kappa(rater_a: list[Any], rater_b: list[Any]) -> float:
    """Calculate Cohen's kappa for inter-rater agreement."""
    n = len(rater_a)
    if n == 0 or len(rater_b) != n:
        return 0.0

    categories = list(set(rater_a).union(set(rater_b)))
    if len(categories) <= 1:
        return 1.0

    # Observed agreement
    po = sum(1 for a, b in zip(rater_a, rater_b, strict=False) if a == b) / n

    # Expected chance agreement
    pe = 0.0
    for cat in categories:
        count_a = sum(1 for a in rater_a if a == cat)
        count_b = sum(1 for b in rater_b if b == cat)
        pe += (count_a / n) * (count_b / n)

    if pe >= 1.0:
        return 1.0

    return round((po - pe) / (1.0 - pe), 4)


def calculate_confusion_matrix(
    actuals: list[str],
    predictions: list[str],
) -> dict[str, dict[str, int]]:
    """Compute confusion matrix {actual: {predicted: count}}."""
    classes = sorted(list(set(actuals).union(set(predictions))))
    matrix: dict[str, dict[str, int]] = {a: {p: 0 for p in classes} for a in classes}
    for a, p in zip(actuals, predictions, strict=False):
        matrix[a][p] += 1
    return matrix
