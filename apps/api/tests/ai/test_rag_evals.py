import math

import pytest

from app.ai.evals.metrics import (
    bootstrap_confidence_interval,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    paired_bootstrap_test,
    summarize_metric,
)
from app.ai.evals.runner import load_dataset


def test_metric_recall_at_k():
    """Verify Recall@K calculation."""
    retrieved = ["c1", "c2", "c3", "c4", "c5"]
    expected = ["c2", "c5", "c9"]

    # At k=2, only c2 is in retrieved[:2] -> 1/3
    assert calculate_recall_at_k(retrieved, expected, k=2) == pytest.approx(1 / 3)
    # At k=5, c2 and c5 are in retrieved[:5] -> 2/3
    assert calculate_recall_at_k(retrieved, expected, k=5) == pytest.approx(2 / 3)
    # When expected is empty
    assert calculate_recall_at_k(retrieved, [], k=5) == 0.0


def test_metric_hit_rate():
    """Verify HitRate@K calculation."""
    retrieved = ["c1", "c2", "c3"]
    expected = ["c2", "c9"]

    assert calculate_hit_rate(retrieved, expected, k=1) == 0.0  # c1 not in expected
    assert calculate_hit_rate(retrieved, expected, k=2) == 1.0  # c2 in retrieved[:2]
    assert calculate_hit_rate(retrieved, ["c99"], k=3) == 0.0


def test_metric_mrr():
    """Verify MRR calculation against hand-computed reciprocal ranks."""
    expected = ["target"]

    # Rank 1 -> 1.0
    assert calculate_mrr(["target", "c2", "c3"], expected) == 1.0
    # Rank 2 -> 0.5
    assert calculate_mrr(["c1", "target", "c3"], expected) == 0.5
    # Rank 3 -> 1/3
    assert calculate_mrr(["c1", "c2", "target"], expected) == pytest.approx(1 / 3)
    # Not found -> 0.0
    assert calculate_mrr(["c1", "c2", "c3"], expected) == 0.0


def test_metric_ndcg_at_k():
    """Verify nDCG@K binary relevance calculation."""
    expected = ["target"]
    # Perfect rank 1: dcg = 1/log2(2) = 1.0, idcg = 1.0 -> ndcg = 1.0
    assert calculate_ndcg_at_k(["target", "c2"], expected, k=2) == 1.0

    # Rank 2: dcg = 1/log2(3), idcg = 1/log2(2) = 1.0 -> ndcg = 1/log2(3) = 0.6309
    expected_ndcg = (1.0 / math.log2(3)) / (1.0 / math.log2(2))
    assert calculate_ndcg_at_k(["c1", "target"], expected, k=2) == pytest.approx(expected_ndcg)

    # Empty expected
    assert calculate_ndcg_at_k(["c1", "c2"], [], k=2) == 0.0


def test_bootstrap_confidence_interval():
    """Verify bootstrap CI produces sensible bounds containing the mean."""
    values = [0.8, 0.9, 0.7, 1.0, 0.85, 0.95, 0.6, 0.75, 0.88, 0.92]
    mean, ci_low, ci_high = bootstrap_confidence_interval(values, n_resamples=500, ci=0.95, seed=42)

    assert ci_low <= mean <= ci_high
    assert 0.6 <= ci_low
    assert ci_high <= 1.0

    summary = summarize_metric(values)
    assert summary.mean == mean
    assert summary.sample_size == len(values)


def test_paired_bootstrap_test():
    """Verify paired bootstrap test detects significant difference."""
    # Clearly superior system
    scores_a = [1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 1.0, 1.0, 1.0, 1.0]
    scores_b = [0.1, 0.2, 0.1, 0.0, 0.3, 0.1, 0.2, 0.0, 0.1, 0.2]
    p_val = paired_bootstrap_test(scores_a, scores_b, n_resamples=200, seed=42)
    assert p_val < 0.05

    # Identical systems
    p_val_identical = paired_bootstrap_test(scores_a, scores_a, n_resamples=200, seed=42)
    assert p_val_identical == 1.0


def test_dataset_loading_and_filtering(tmp_path):
    """Verify load_dataset excludes draft cases and filters by split."""
    ds_file = tmp_path / "test_ds.jsonl"
    lines = [
        '{"id": "c1", "split": "dev", "language": "en", "type": "answerable", '
        '"question": "Q1", "expected_document_ids": ["d1"], "expected_chunk_ids": [], '
        '"notes": "", "status": "reviewed"}\n',
        '{"id": "c2", "split": "test", "language": "ml", "type": "answerable", '
        '"question": "Q2", "expected_document_ids": ["d2"], "expected_chunk_ids": [], '
        '"notes": "", "status": "reviewed"}\n',
        '{"id": "c3", "split": "dev", "language": "en", "type": "refusal_expected", '
        '"question": "Q3", "expected_document_ids": [], "expected_chunk_ids": [], '
        '"notes": "", "status": "draft"}\n',
    ]
    ds_file.write_text("".join(lines), encoding="utf-8")

    all_cases = load_dataset(ds_file)
    assert len(all_cases) == 2  # draft case c3 excluded
    assert {c.id for c in all_cases} == {"c1", "c2"}

    dev_cases = load_dataset(ds_file, split="dev")
    assert len(dev_cases) == 1
    assert dev_cases[0].id == "c1"

    test_cases = load_dataset(ds_file, split="test")
    assert len(test_cases) == 1
    assert test_cases[0].id == "c2"
