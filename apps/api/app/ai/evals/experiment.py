import argparse
import asyncio
import datetime
import logging
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence, cast

from app.ai.evals.metrics import (
    calculate_answer_bearing_hit,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    summarize_metric,
)
from app.ai.evals.models import (
    AnswerMetricsReport,
    EvalErrorCase,
    ExperimentRunReport,
    RAGEvalCase,
    RetrievalMetricsReport,
)
from app.ai.evals.review import load_cases_jsonl
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.dependencies import get_llm_gateway
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.answer import KnowledgeAnswerService
from app.ai.rag.answer_models import KnowledgeQuestionRequest
from app.ai.rag.dependencies import get_embedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import BaseReranker, HybridRetriever, LexicalTrigramReranker, RetrievalConfig
from app.ai.rag.smoke import cosine_similarity
from app.db.session import get_async_session_factory
from app.models.enums import ConsentType
from app.models.user import Consent, User
from app.services.verified_contacts import get_all_verified_contacts

logger = logging.getLogger("app.ai.evals.experiment")

DEFAULT_REPORTS_DIR = Path("evals/reports")


def extract_numbers(text: str) -> list[str]:
    """Extract numeric tokens (phone numbers, sections, percentages, amounts)."""
    return re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", text)


def extract_contacts_and_urls(text: str) -> list[str]:
    """Extract helplines, phone numbers, and URLs."""
    phones = re.findall(r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b|\b1930\b|\b14448\b|\b112\b", text)
    urls = re.findall(r"https?://[^\s]+|www\.[^\s]+", text)
    return phones + urls


async def get_or_create_eval_user(session: Any) -> User:
    import uuid

    u_id = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
    user = await session.get(User, u_id)
    if not user:
        user = User(
            id=u_id,
            email="rag_eval_harness@float.internal",
            normalized_email="rag_eval_harness@float.internal",
            hashed_password="eval_dummy_hash",
            full_name="RAG Eval Harness",
            is_active=True,
        )
        session.add(user)
        consent = Consent(
            user_id=u_id,
            consent_type=ConsentType.AI_DATA_PROCESSING,
            consent_version="v1.0",
        )
        session.add(consent)
        await session.commit()
    return cast(User, user)


async def run_experiment(
    cases: Sequence[RAGEvalCase],
    config: RetrievalConfig,
    mode: str = "hybrid",
    reranker_on: bool = False,
    prompt_version: str = "v1",
    provider: str = "fake",
    split: str = "dev",
    sweep_thresholds: bool = False,
    output_dir: Path | str = DEFAULT_REPORTS_DIR,
    session_factory: Any = None,
) -> ExperimentRunReport:
    """Run an evaluation experiment across retrieval and answer stages."""
    session_factory = session_factory or get_async_session_factory()
    reranker: BaseReranker | None = LexicalTrigramReranker() if reranker_on else None

    # Embedder setup
    try:
        embedder = get_embedder()
    except Exception:
        embedder = FakeEmbedder()

    # LLM Gateway setup
    if provider == "configured":
        gateway = get_llm_gateway()
    else:
        fake_adapter = FakeProvider()
        gateway = LLMGateway(config=LLMConfig(provider="fake", approved_for_real_data=True), adapter=fake_adapter)

    verified_contacts_list: list[str] = ["1930", "112", "14448"]
    for item in get_all_verified_contacts():
        for k in ("toll_free_number", "alternate_number", "website"):
            val = item.get(k)
            if val:
                verified_contacts_list.append(str(val))
                verified_contacts_list.extend(re.findall(r"\b\d+\b", str(val)))

    # Metric accumulators
    overall_r5: list[float] = []
    overall_r10: list[float] = []
    overall_mrr: list[float] = []
    overall_ndcg: list[float] = []
    overall_hit: list[float] = []
    overall_abh: list[float] = []

    by_lang_retrieval: dict[str, dict[str, list[float]]] = {}
    by_lang_answer: dict[str, dict[str, list[float]]] = {}

    status_acc_list: list[float] = []
    citation_valid_list: list[float] = []
    citation_support_list: list[float] = []
    invented_contact_list: list[float] = []
    numeric_grounding_list: list[float] = []
    fact_coverage_list: list[float] = []
    semantic_sim_list: list[float] = []

    worst_cases: list[EvalErrorCase] = []
    latencies: list[float] = []

    answerable_scores: list[float] = []
    unanswerable_scores: list[float] = []

    active_cases = [c for c in cases if c.status == "reviewed" and (split == "all" or c.split == split)]
    excluded_unreviewed = [c for c in cases if c.status != "reviewed" and (split == "all" or c.split == split)]
    excluded_count = len(excluded_unreviewed)
    if not active_cases:
        # If no reviewed cases yet in file, fall back to evaluating provided cases
        active_cases = list(cases)

    async with session_factory() as session:
        eval_user = await get_or_create_eval_user(session)

        # Adjust config for mode (vector-only, keyword-only, hybrid)
        run_cfg = config
        if reranker_on:
            run_cfg = replace(run_cfg, reranker_model="lexical_trigram")
        if mode == "vector-only":
            run_cfg = RetrievalConfig(
                vector_candidates=config.vector_candidates,
                keyword_candidates=0,
                return_size=config.return_size,
                rrf_k=config.rrf_k,
                min_evidence_score=config.min_evidence_score,
                reranker_model="lexical_trigram" if reranker_on else None,
            )
        elif mode == "keyword-only":
            run_cfg = RetrievalConfig(
                vector_candidates=0,
                keyword_candidates=config.keyword_candidates,
                return_size=config.return_size,
                rrf_k=config.rrf_k,
                min_evidence_score=config.min_evidence_score,
                reranker_model="lexical_trigram" if reranker_on else None,
            )

        retriever = HybridRetriever(
            session=session,
            embedder=embedder,
            config=run_cfg,
            reranker=reranker,
        )
        answer_service = KnowledgeAnswerService(
            session=session,
            retriever=retriever,
            gateway=gateway,
        )

        for idx, case in enumerate(active_cases, start=1):
            if idx % 15 == 0 or idx == len(active_cases):
                logger.info("Processed %d/%d cases...", idx, len(active_cases))
            t0 = time.monotonic()
            evidence = await retriever.retrieve(case.question)
            lat_ms = (time.monotonic() - t0) * 1000.0
            latencies.append(lat_ms)

            retrieved_chunk_ids = [c.chunk_id for c in evidence.chunks]
            top_evidence_score = evidence.top_vector_score or evidence.top_fused_score

            # Retrieval evaluation for answerable cases
            if case.type == "answerable":
                answerable_scores.append(top_evidence_score)
                expected_targets = [case.gold_chunk_id] if case.gold_chunk_id else []
                acceptable_targets = case.acceptable_chunk_ids

                r5 = calculate_recall_at_k(retrieved_chunk_ids, expected_targets, k=5)
                r10 = calculate_recall_at_k(retrieved_chunk_ids, expected_targets, k=10)
                mrr = calculate_mrr(retrieved_chunk_ids, expected_targets)
                ndcg = calculate_ndcg_at_k(retrieved_chunk_ids, expected_targets, k=5)
                hit = calculate_hit_rate(retrieved_chunk_ids, expected_targets, k=5)
                abh = calculate_answer_bearing_hit(retrieved_chunk_ids, acceptable_targets, k=5)

                overall_r5.append(r5)
                overall_r10.append(r10)
                overall_mrr.append(mrr)
                overall_ndcg.append(ndcg)
                overall_hit.append(hit)
                overall_abh.append(abh)

                lang_group = by_lang_retrieval.setdefault(
                    case.language,
                    {"r5": [], "r10": [], "mrr": [], "ndcg": [], "hit": [], "abh": []},
                )
                lang_group["r5"].append(r5)
                lang_group["r10"].append(r10)
                lang_group["mrr"].append(mrr)
                lang_group["ndcg"].append(ndcg)
                lang_group["hit"].append(hit)
                lang_group["abh"].append(abh)

                if hit == 0.0 and len(expected_targets) > 0:
                    worst_cases.append(
                        EvalErrorCase(
                            case_id=case.id,
                            language=case.language,
                            type=case.type,
                            question=case.question,
                            reason_code="retrieval_miss",
                            details=(
                                f"Expected gold chunk {case.gold_chunk_id} not retrieved in "
                                f"top {len(retrieved_chunk_ids)}"
                            ),
                            retrieved_chunk_ids=retrieved_chunk_ids[:5],
                            gold_chunk_id=case.gold_chunk_id,
                        )
                    )
            else:
                unanswerable_scores.append(top_evidence_score)

            # Answer Generation Stage
            try:
                ans_resp = await answer_service.answer(
                    KnowledgeQuestionRequest(
                        question=case.question,
                        language_hint=case.language,
                    ),
                    eval_user,
                )
                pred_status = ans_resp.status
                ans_text = ans_resp.answer
                citations = ans_resp.citations
            except Exception as e:
                logger.error("Answer generation exception on case %s: %s", case.id, e)
                pred_status = "insufficient_evidence"
                ans_text = ""
                citations = []

            # 1. Status Accuracy
            if case.type == "answerable":
                expected_st = "answered"
            elif case.type == "refusal_expected":
                expected_st = "refused"
            else:
                expected_st = "insufficient_evidence"

            st_match = 1.0 if pred_status == expected_st else 0.0
            status_acc_list.append(st_match)

            if st_match == 0.0:
                worst_cases.append(
                    EvalErrorCase(
                        case_id=case.id,
                        language=case.language,
                        type=case.type,
                        question=case.question,
                        reason_code="wrong_abstention",
                        details=f"Expected status {expected_st}, got {pred_status}",
                        predicted_status=pred_status,
                        expected_status=expected_st,
                    )
                )

            # 2. Citation Validity & Support
            if citations:
                valid_cites = [c for c in citations if c.chunk_id in retrieved_chunk_ids]
                cit_val = len(valid_cites) / len(citations)
                cit_sup = 1.0 if all(c.chunk_id in retrieved_chunk_ids for c in citations) else 0.5
            else:
                cit_val = 1.0 if pred_status != "answered" else 0.0
                cit_sup = 1.0 if pred_status != "answered" else 0.0
            citation_valid_list.append(cit_val)
            citation_support_list.append(cit_sup)

            if cit_val < 1.0:
                worst_cases.append(
                    EvalErrorCase(
                        case_id=case.id,
                        language=case.language,
                        type=case.type,
                        question=case.question,
                        reason_code="bad_citation",
                        details="Hallucinated or unverified citation chunk ID in answer",
                    )
                )

            # 3. Invented Contact Rate (Target: 0.0)
            contacts_found = extract_contacts_and_urls(ans_text)
            invented = 0
            for c_val in contacts_found:
                if c_val not in verified_contacts_list and not any(c_val in ch.text for ch in evidence.chunks):
                    invented += 1
            inv_rate = 1.0 if invented > 0 else 0.0
            invented_contact_list.append(inv_rate)

            # 4. Numeric Grounding (Target: 1.0)
            nums_in_ans = extract_numbers(ans_text)
            if nums_in_ans:
                grounded_nums = sum(
                    1
                    for num in nums_in_ans
                    if any(num in ch.text for ch in evidence.chunks) or num in case.question or num in ("1930", "112")
                )
                num_score = 1.0 if grounded_nums == len(nums_in_ans) else 0.0
            else:
                num_score = 1.0
            numeric_grounding_list.append(num_score)

            if num_score < 1.0 or inv_rate > 0.0:
                worst_cases.append(
                    EvalErrorCase(
                        case_id=case.id,
                        language=case.language,
                        type=case.type,
                        question=case.question,
                        reason_code="validation_failure",
                        details="Invented contact or ungrounded numeric claim found in answer text",
                    )
                )

            # 5. Required Fact Coverage
            if case.required_facts:
                covered = sum(1 for f in case.required_facts if f.lower() in ans_text.lower())
                cov_rate = covered / len(case.required_facts)
            else:
                cov_rate = 1.0 if pred_status == expected_st else 0.0
            fact_coverage_list.append(cov_rate)

            # 6. Semantic Similarity to Reference Answer (Embedding Cosine)
            if provider != "fake" and case.reference_answer and ans_text:
                try:
                    v_ans = embedder.embed_query(ans_text[:300])
                    v_ref = embedder.embed_query(case.reference_answer[:300])
                    sim = max(0.0, float(cosine_similarity(v_ans, v_ref)))
                except Exception:
                    sim = 0.5
            else:
                sim = 1.0 if pred_status == expected_st else 0.0
            semantic_sim_list.append(sim)

            # Track answer metrics by language
            lang_ans = by_lang_answer.setdefault(
                case.language,
                {
                    "status_acc": [],
                    "cit_val": [],
                    "cit_sup": [],
                    "inv_cont": [],
                    "num_grd": [],
                    "fact_cov": [],
                    "sem_sim": [],
                },
            )
            lang_ans["status_acc"].append(st_match)
            lang_ans["cit_val"].append(cit_val)
            lang_ans["cit_sup"].append(cit_sup)
            lang_ans["inv_cont"].append(inv_rate)
            lang_ans["num_grd"].append(num_score)
            lang_ans["fact_cov"].append(cov_rate)
            lang_ans["sem_sim"].append(sim)

    # Threshold sweep analysis on calibrated vector evidence score
    threshold_sweep: dict[str, dict[str, float]] = {}
    if sweep_thresholds and (answerable_scores or unanswerable_scores):
        for th in [0.76, 0.78, 0.80, 0.82, 0.84, 0.85, 0.86, 0.88, 0.90]:
            fa = sum(1 for s in answerable_scores if s < th) / len(answerable_scores) if answerable_scores else 0.0
            n_unans = len(unanswerable_scores)
            f_ans = sum(1 for s in unanswerable_scores if s >= th) / n_unans if n_unans else 0.0
            threshold_sweep[f"th_{th:.2f}"] = {
                "threshold": th,
                "false_abstain_rate": round(fa, 4),
                "false_answer_rate": round(f_ans, 4),
            }

    # Compile Overall Retrieval Report
    retrieval_overall = RetrievalMetricsReport(
        recall_at_5=summarize_metric(overall_r5),
        recall_at_10=summarize_metric(overall_r10),
        mrr=summarize_metric(overall_mrr),
        ndcg_at_5=summarize_metric(overall_ndcg),
        hit_rate=summarize_metric(overall_hit),
        answer_bearing_hit=summarize_metric(overall_abh),
        sample_size=len(overall_r5),
    )

    retrieval_by_lang: dict[str, RetrievalMetricsReport] = {}
    for lang_code, m in by_lang_retrieval.items():
        retrieval_by_lang[lang_code] = RetrievalMetricsReport(
            recall_at_5=summarize_metric(m["r5"]),
            recall_at_10=summarize_metric(m["r10"]),
            mrr=summarize_metric(m["mrr"]),
            ndcg_at_5=summarize_metric(m["ndcg"]),
            hit_rate=summarize_metric(m["hit"]),
            answer_bearing_hit=summarize_metric(m.get("abh", [])),
            sample_size=len(m["r5"]),
        )

    # Compile Overall Answer Report
    answer_overall = AnswerMetricsReport(
        status_accuracy=summarize_metric(status_acc_list),
        citation_validity=summarize_metric(citation_valid_list),
        citation_support=summarize_metric(citation_support_list),
        invented_contact_rate=summarize_metric(invented_contact_list),
        numeric_grounding=summarize_metric(numeric_grounding_list),
        required_fact_coverage=summarize_metric(fact_coverage_list),
        semantic_similarity=summarize_metric(semantic_sim_list),
        sample_size=len(status_acc_list),
    )

    answer_by_lang: dict[str, AnswerMetricsReport] = {}
    for lang_code, m in by_lang_answer.items():
        answer_by_lang[lang_code] = AnswerMetricsReport(
            status_accuracy=summarize_metric(m["status_acc"]),
            citation_validity=summarize_metric(m["cit_val"]),
            citation_support=summarize_metric(m["cit_sup"]),
            invented_contact_rate=summarize_metric(m["inv_cont"]),
            numeric_grounding=summarize_metric(m["num_grd"]),
            required_fact_coverage=summarize_metric(m["fact_cov"]),
            semantic_similarity=summarize_metric(m["sem_sim"]),
            sample_size=len(m["status_acc"]),
        )

    # Sort latencies for percentiles
    latencies.sort()
    n_lat = len(latencies)
    p50 = latencies[int(n_lat * 0.5)] if n_lat > 0 else 0.0
    p95 = latencies[min(n_lat - 1, int(n_lat * 0.95))] if n_lat > 0 else 0.0

    run_id = f"run_{int(time.time())}_{mode}"
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    report = ExperimentRunReport(
        run_id=run_id,
        timestamp=ts,
        config={
            "mode": mode,
            "vector_candidates": run_cfg.vector_candidates,
            "keyword_candidates": run_cfg.keyword_candidates,
            "return_size": run_cfg.return_size,
            "rrf_k": run_cfg.rrf_k,
            "min_evidence_score": run_cfg.min_evidence_score,
            "reranker": "lexical_trigram" if reranker_on else "none",
            "prompt_version": prompt_version,
            "provider": provider,
        },
        config_hash=run_cfg.config_hash(),
        split=split,
        sample_size=len(active_cases),
        excluded_unreviewed_count=excluded_count,
        retrieval_overall=retrieval_overall,
        retrieval_by_language=retrieval_by_lang,
        answer_overall=answer_overall,
        answer_by_language=answer_by_lang,
        latency_p50_ms=round(p50, 2),
        latency_p95_ms=round(p95, 2),
        worst_cases=worst_cases,
        abstention_threshold_sweep=threshold_sweep,
    )

    # Write report JSON
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"{run_id}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    logger.info("Saved experiment report to: %s", report_file)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Float RAG Experiment Runner")
    parser.add_argument("--dataset", type=str, default="evals/data/rag_dataset_draft.jsonl", help="Dataset path")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev", help="Dataset split to evaluate")
    parser.add_argument(
        "--mode",
        choices=["vector-only", "keyword-only", "hybrid", "all"],
        default="hybrid",
        help="Retrieval mode",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of retrieved chunks")
    parser.add_argument("--rrf-k", type=int, default=60, help="RRF k constant")
    parser.add_argument("--reranker", action="store_true", help="Enable reranker")
    parser.add_argument("--threshold", type=float, default=0.84, help="Min evidence score threshold")
    parser.add_argument("--sweep-thresholds", action="store_true", help="Perform threshold sweep")
    parser.add_argument("--prompt-version", type=str, default="v1", help="RAG prompt version")
    parser.add_argument("--provider", choices=["fake", "configured"], default="fake", help="LLM provider")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_REPORTS_DIR), help="Output reports directory")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    cases = load_cases_jsonl(args.dataset, split=args.split, only_reviewed=False)
    if not cases:
        logger.warning("No cases found in %s. Generating fallback demo cases...", args.dataset)
        from app.ai.evals.datagen import generate_dataset

        cases = asyncio.run(generate_dataset(target_count=20, provider="fake"))

    modes = ["vector-only", "keyword-only", "hybrid"] if args.mode == "all" else [args.mode]

    for m in modes:
        cfg = RetrievalConfig(
            vector_candidates=20,
            keyword_candidates=20,
            return_size=args.top_k,
            rrf_k=args.rrf_k,
            min_evidence_score=args.threshold,
        )
        logger.info("Running experiment mode: %s...", m)
        rep = asyncio.run(
            run_experiment(
                cases=cases,
                config=cfg,
                mode=m,
                reranker_on=args.reranker,
                prompt_version=args.prompt_version,
                provider=args.provider,
                split=args.split,
                sweep_thresholds=args.sweep_thresholds,
                output_dir=args.output_dir,
            )
        )
        print(f"\n=== Experiment Result: {m} (split: {args.split}) ===")
        if args.split == "dev":
            print(
                "[Notice] Dev set: synthetic template questions "
                "(100% contain the gold heading path); not representative of real users."
            )
        print(f"Sample size: {rep.sample_size} (Excluded unreviewed: {rep.excluded_unreviewed_count})")
        if rep.retrieval_overall.answer_bearing_hit:
            abh_m = rep.retrieval_overall.answer_bearing_hit
            print(
                f"Headline Metric - Answer-Bearing Hit@5: {abh_m.mean:.4f} "
                f"[{abh_m.ci_95_low:.4f}, {abh_m.ci_95_high:.4f}]"
            )
        print(
            f"Headline Metric - MRR:                 {rep.retrieval_overall.mrr.mean:.4f} "
            f"[{rep.retrieval_overall.mrr.ci_95_low:.4f}, {rep.retrieval_overall.mrr.ci_95_high:.4f}]"
        )
        print(
            f"Headline Metric - nDCG@5:              {rep.retrieval_overall.ndcg_at_5.mean:.4f} "
            f"[{rep.retrieval_overall.ndcg_at_5.ci_95_low:.4f}, {rep.retrieval_overall.ndcg_at_5.ci_95_high:.4f}]"
        )
        if rep.answer_overall:
            print(f"Headline Metric - Status Accuracy:     {rep.answer_overall.status_accuracy.mean:.4f}")
            print(f"Citation Valid:  {rep.answer_overall.citation_validity.mean:.4f}")
            print(f"Invented Contacts: {rep.answer_overall.invented_contact_rate.mean:.4f}")
            print(f"Numeric Grounding: {rep.answer_overall.numeric_grounding.mean:.4f}")
        print(
            f"[Diagnostic only] Recall@5 (template-biased): {rep.retrieval_overall.recall_at_5.mean:.4f} "
            f"[{rep.retrieval_overall.recall_at_5.ci_95_low:.4f}, {rep.retrieval_overall.recall_at_5.ci_95_high:.4f}]"
        )
        print(f"Latency p50: {rep.latency_p50_ms}ms, p95: {rep.latency_p95_ms}ms")
        print(f"Worst cases recorded: {len(rep.worst_cases)}")


if __name__ == "__main__":
    main()
