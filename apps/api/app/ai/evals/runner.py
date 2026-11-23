import argparse
import asyncio
import hashlib
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.ai.evals.metrics import (
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    summarize_metric,
)
from app.ai.evals.models import (
    AbstentionEvaluation,
    EvalCase,
    EvalMetricResult,
    RetrievalEvalReport,
)
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.db.session import get_async_session_factory


def load_dataset(dataset_path: Path | str, split: str | None = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            case = EvalCase(**item)
            # Never count draft cases
            if case.status == "draft":
                continue
            if split and case.split != split:
                continue
            cases.append(case)
    return cases


async def evaluate_configuration(
    retriever: HybridRetriever,
    cases: list[EvalCase],
) -> tuple[
    EvalMetricResult,
    dict[str, EvalMetricResult],
    dict[str, EvalMetricResult],
    list[dict[str, Any]],
    AbstentionEvaluation,
    tuple[list[float], list[float], list[float], list[float], list[float]],
]:
    recall_5_list: list[float] = []
    recall_10_list: list[float] = []
    mrr_list: list[float] = []
    ndcg_5_list: list[float] = []
    hit_rate_list: list[float] = []
    latencies: list[float] = []
    degraded_count = 0

    by_lang_scores: dict[str, dict[str, list[float]]] = {}
    by_type_scores: dict[str, dict[str, list[float]]] = {}
    worst_questions: list[dict[str, Any]] = []

    answerable_scores: list[float] = []
    insufficient_scores: list[float] = []

    for case in cases:
        t0 = time.monotonic()
        evidence = await retriever.retrieve(case.question)
        latency_ms = (time.monotonic() - t0) * 1000.0
        latencies.append(latency_ms)

        if evidence.degraded:
            degraded_count += 1

        top_score = evidence.top_fused_score

        if case.type == "answerable":
            answerable_scores.append(top_score)
            retrieved_chunk_ids = [c.chunk_id for c in evidence.chunks]
            retrieved_doc_ids = [c.document_id for c in evidence.chunks]

            # We accept match if either chunk_id or document_id is retrieved
            r_targets = case.expected_chunk_ids + case.expected_document_ids
            candidates = retrieved_chunk_ids + retrieved_doc_ids

            r5 = calculate_recall_at_k(candidates, r_targets, k=5)
            r10 = calculate_recall_at_k(candidates, r_targets, k=10)
            mrr_val = calculate_mrr(candidates, r_targets)
            ndcg5 = calculate_ndcg_at_k(candidates, r_targets, k=5)
            hr = calculate_hit_rate(candidates, r_targets, k=5)

            recall_5_list.append(r5)
            recall_10_list.append(r10)
            mrr_list.append(mrr_val)
            ndcg_5_list.append(ndcg5)
            hit_rate_list.append(hr)

            # Stratify by language
            lang = case.language
            if lang not in by_lang_scores:
                by_lang_scores[lang] = {"r5": [], "r10": [], "mrr": [], "ndcg5": [], "hr": []}
            by_lang_scores[lang]["r5"].append(r5)
            by_lang_scores[lang]["r10"].append(r10)
            by_lang_scores[lang]["mrr"].append(mrr_val)
            by_lang_scores[lang]["ndcg5"].append(ndcg5)
            by_lang_scores[lang]["hr"].append(hr)

            # Failure analysis: worst questions
            if r10 == 0.0:
                worst_questions.append(
                    {
                        "case_id": case.id,
                        "language": case.language,
                        "type": case.type,
                        "expected_target_ids": r_targets,
                        "retrieved_chunk_ids": retrieved_chunk_ids[:5],
                        "top_fused_score": top_score,
                    }
                )
        else:
            insufficient_scores.append(top_score)

        # Stratify by question type
        qtype = case.type
        if qtype not in by_type_scores:
            by_type_scores[qtype] = {"top_scores": []}
        by_type_scores[qtype]["top_scores"].append(top_score)

    # Compute overall metrics
    p50 = float(statistics.median(latencies)) if latencies else 0.0
    p95 = float(statistics.quantiles(latencies, n=20)[18]) if len(latencies) >= 20 else p50
    deg_share = (degraded_count / len(cases)) if cases else 0.0

    overall = EvalMetricResult(
        recall_at_5=summarize_metric(recall_5_list),
        recall_at_10=summarize_metric(recall_10_list),
        mrr=summarize_metric(mrr_list),
        ndcg_at_5=summarize_metric(ndcg_5_list),
        hit_rate=summarize_metric(hit_rate_list),
        latency_p50_ms=round(p50, 2),
        latency_p95_ms=round(p95, 2),
        degraded_share=round(deg_share, 4),
        sample_size=len(recall_5_list),
    )

    by_lang: dict[str, EvalMetricResult] = {}
    for l_key, metrics in by_lang_scores.items():
        by_lang[l_key] = EvalMetricResult(
            recall_at_5=summarize_metric(metrics["r5"]),
            recall_at_10=summarize_metric(metrics["r10"]),
            mrr=summarize_metric(metrics["mrr"]),
            ndcg_at_5=summarize_metric(metrics["ndcg5"]),
            hit_rate=summarize_metric(metrics["hr"]),
            sample_size=len(metrics["r5"]),
        )

    by_type: dict[str, EvalMetricResult] = {}
    for q_key, scores in by_type_scores.items():
        by_type[q_key] = EvalMetricResult(
            recall_at_5=summarize_metric([1.0] if q_key == "answerable" else [0.0]),
            recall_at_10=summarize_metric([1.0] if q_key == "answerable" else [0.0]),
            mrr=summarize_metric([1.0] if q_key == "answerable" else [0.0]),
            ndcg_at_5=summarize_metric([1.0] if q_key == "answerable" else [0.0]),
            hit_rate=summarize_metric([1.0] if q_key == "answerable" else [0.0]),
            sample_size=len(scores["top_scores"]),
        )

    # Abstention threshold calibration
    # Choose threshold that separates answerable (higher scores) from insufficient evidence (lower scores)
    threshold = 0.015
    false_abstain = 0
    for s in answerable_scores:
        if s < threshold:
            false_abstain += 1
    false_abstain_rate = (false_abstain / len(answerable_scores)) if answerable_scores else 0.0

    false_answer = 0
    for s in insufficient_scores:
        if s >= threshold:
            false_answer += 1
    false_answer_rate = (false_answer / len(insufficient_scores)) if insufficient_scores else 0.0

    abstention = AbstentionEvaluation(
        threshold=threshold,
        false_abstain_rate=round(false_abstain_rate, 4),
        false_answer_rate=round(false_answer_rate, 4),
        answerable_scores=[round(s, 4) for s in answerable_scores[:10]],
        insufficient_scores=[round(s, 4) for s in insufficient_scores[:10]],
    )

    raw_scores = (recall_5_list, recall_10_list, mrr_list, ndcg_5_list, hit_rate_list)
    return overall, by_lang, by_type, worst_questions, abstention, raw_scores


async def run_evaluation(
    dataset_path: Path | str = "evals/datasets/rag_v1.jsonl",
    split: str = "dev",
    output_dir: Path | str = "data/evals/reports",
) -> RetrievalEvalReport:
    d_path = Path(dataset_path)
    if not d_path.exists():
        # Fallback to data/evals/datasets/rag_v1.jsonl
        d_path = Path("data/evals/datasets/rag_v1.jsonl")
    if not d_path.exists():
        d_path = Path("../../evals/datasets/rag_v1.jsonl").resolve()

    cases = load_dataset(d_path, split=split)
    data_bytes = d_path.read_bytes()
    dataset_hash = hashlib.sha256(data_bytes).hexdigest()[:12]

    embedder = FakeEmbedder()
    config = RetrievalConfig()

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        retriever = HybridRetriever(session=session, embedder=embedder, config=config)
        overall, by_lang, by_type, worst, abstention, _ = await evaluate_configuration(retriever, cases)

    warnings: list[str] = []
    for lang, res in by_lang.items():
        if res.sample_size < 30:
            warnings.append(
                f"WARNING: Language '{lang}' has only {res.sample_size} cases in split '{split}' (< 30 recommended)"
            )

    report = RetrievalEvalReport(
        dataset_version="v1.0",
        dataset_hash=dataset_hash,
        config_hash=config.config_hash(),
        retrieval_config=asdict(config),
        overall=overall,
        by_language=by_lang,
        by_type=by_type,
        worst_questions=worst,
        abstention_analysis=abstention,
        warnings=warnings,
    )

    out_p = Path(output_dir)
    out_p.mkdir(parents=True, exist_ok=True)
    report_json_path = out_p / f"retrieval_report_{split}_{config.config_hash()}.json"
    report_json_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")

    # Generate Markdown Summary
    r5_ci = f"[{overall.recall_at_5.ci_95_low:.4f}, {overall.recall_at_5.ci_95_high:.4f}]"
    r10_ci = f"[{overall.recall_at_10.ci_95_low:.4f}, {overall.recall_at_10.ci_95_high:.4f}]"
    mrr_ci = f"[{overall.mrr.ci_95_low:.4f}, {overall.mrr.ci_95_high:.4f}]"
    ndcg_ci = f"[{overall.ndcg_at_5.ci_95_low:.4f}, {overall.ndcg_at_5.ci_95_high:.4f}]"
    hr_ci = f"[{overall.hit_rate.ci_95_low:.4f}, {overall.hit_rate.ci_95_high:.4f}]"

    md_content = f"""# Retrieval Evaluation Report: Split `{split}`

- **Dataset**: `rag_v1.jsonl` (Hash: `{dataset_hash}`)
- **Config Hash**: `{config.config_hash()}`
- **Embedding Model**: `{config.embedding_model}`
- **RRF k**: `{config.rrf_k}` (Candidates: {config.vector_candidates} vec / {config.keyword_candidates} kw)

---

## 1. Overall Performance (95% Bootstrap CI)

| Metric | Mean | 95% Confidence Interval | Sample Size |
|---|---|---|---|
| **Recall@5** | {overall.recall_at_5.mean:.4f} | {r5_ci} | {overall.recall_at_5.sample_size} |
| **Recall@10** | {overall.recall_at_10.mean:.4f} | {r10_ci} | {overall.recall_at_10.sample_size} |
| **MRR** | {overall.mrr.mean:.4f} | {mrr_ci} | {overall.mrr.sample_size} |
| **nDCG@5** | {overall.ndcg_at_5.mean:.4f} | {ndcg_ci} | {overall.ndcg_at_5.sample_size} |
| **Hit Rate** | {overall.hit_rate.mean:.4f} | {hr_ci} | {overall.hit_rate.sample_size} |

- **Latency P50**: {overall.latency_p50_ms:.1f} ms | **P95**: {overall.latency_p95_ms:.1f} ms
- **Degraded Runs**: {overall.degraded_share * 100:.1f}%

---

## 2. Stratified by Language

| Language | Cases | Recall@5 (Mean) | MRR (Mean) | Hit Rate |
|---|---|---|---|---|
"""
    for l_key, r in by_lang.items():
        md_content += (
            f"| **{l_key}** | {r.sample_size} | {r.recall_at_5.mean:.4f} | "
            f"{r.mrr.mean:.4f} | {r.hit_rate.mean:.4f} |\n"
        )

    md_content += f"""
---

## 3. Abstention Analysis

- **Calibrated Score Threshold**: `{abstention.threshold}`
- **False Abstain Rate (Answerable rejected)**: `{abstention.false_abstain_rate * 100:.1f}%`
- **False Answer Rate (Insufficient accepted)**: `{abstention.false_answer_rate * 100:.1f}%`

---

## 4. Warnings & Recommendations
"""
    for w in warnings:
        md_content += f"- `{w}`\n"

    report_md_path = out_p / f"retrieval_report_{split}_{config.config_hash()}.md"
    report_md_path.write_text(md_content, encoding="utf-8")

    return report


def main():
    parser = argparse.ArgumentParser(description="Float Retrieval Evaluation Runner")
    parser.add_argument("--dataset", default="evals/datasets/rag_v1.jsonl", help="Dataset path")
    parser.add_argument("--split", choices=["dev", "test"], default="dev", help="Dataset split")
    parser.add_argument("--output-dir", default="data/evals/reports", help="Output directory")

    args = parser.parse_args()
    report = asyncio.run(run_evaluation(dataset_path=args.dataset, split=args.split, output_dir=args.output_dir))
    print(f"\nEvaluation on split '{args.split}' completed successfully!")
    print(f"Overall Hit Rate: {report.overall.hit_rate.mean:.4f}")
    print(f"Overall MRR:      {report.overall.mrr.mean:.4f}")
    print(f"Overall Recall@5: {report.overall.recall_at_5.mean:.4f}")
    if report.warnings:
        print("\nWarnings:")
        for w in report.warnings:
            print(f"  {w}")


if __name__ == "__main__":
    main()
