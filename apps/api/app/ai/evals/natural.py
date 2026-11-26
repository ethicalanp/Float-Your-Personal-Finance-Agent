"""Natural (non-template) eval workflow: stratified split, abstention calibration, one-shot frozen test.

Usage (from apps/api):
  python -m app.ai.evals.natural split
  python -m app.ai.evals.natural calibrate --reranker BAAI/bge-reranker-v2-m3
  python -m app.ai.evals.natural test --threshold 0.xx --margin 0.xx   # runs ONCE
"""

import argparse
import asyncio
import hashlib
import json
import logging
import math
import random
import re
import stat
import statistics
import time
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import select

from app.ai.evals.experiment import (
    extract_contacts_and_urls,
    extract_numbers,
    get_or_create_eval_user,
)
from app.ai.evals.metrics import summarize_metric
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.answer import KnowledgeAnswerService
from app.ai.rag.answer_models import KnowledgeQuestionRequest
from app.ai.rag.dependencies import get_embedder
from app.ai.rag.policy_guard import PolicyGuard
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.ai.rag.smoke import cosine_similarity
from app.db.session import get_async_session_factory
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.verified_contacts import get_all_verified_contacts

logger = logging.getLogger("app.ai.evals.natural")

DATA_DIR = Path("evals/data")
FRESH_FROZEN = DATA_DIR / "rag_fresh_test_frozen.jsonl"
NATURAL_DEV = DATA_DIR / "rag_natural_dev.jsonl"
NATURAL_TEST = DATA_DIR / "rag_natural_test_frozen.jsonl"
MANIFEST = DATA_DIR / "natural_split_manifest.json"
REPORTS_DIR = Path("evals/reports")
SPLIT_SEED = 20261125
RERANKER_DEFAULT = "BAAI/bge-reranker-v2-m3"


# --------------------------------------------------------------------------- split
def stratified_split(rows: Sequence[dict[str, Any]], seed: int = SPLIT_SEED) -> tuple[list[dict], list[dict]]:
    """Split rows 50/50 within each (type, language) stratum; odd strata alternate who gets the extra case."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["type"], r["language"]), []).append(r)
    rng = random.Random(seed)
    dev: list[dict] = []
    test: list[dict] = []
    give_extra_to_dev = True
    for key in sorted(groups):
        items = sorted(groups[key], key=lambda r: r["id"])
        rng.shuffle(items)
        n = len(items)
        n_dev = n // 2
        if n % 2:
            n_dev += 1 if give_extra_to_dev else 0
            give_extra_to_dev = not give_extra_to_dev
        dev.extend(items[:n_dev])
        test.extend(items[n_dev:])
    return sorted(dev, key=lambda r: r["id"]), sorted(test, key=lambda r: r["id"])


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> str:
    if path.exists():
        path.chmod(stat.S_IWRITE | stat.S_IREAD)
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_text(payload, encoding="utf-8", newline="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def do_split() -> None:
    rows = [json.loads(line) for line in FRESH_FROZEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in rows:
        r["needs_native_review"] = r["language"] in ("ml", "manglish")
    dev, test = stratified_split(rows)
    for r in dev:
        r["split"] = "dev"
    for r in test:
        r["split"] = "test"
    h_dev = _write_jsonl(NATURAL_DEV, dev)
    h_test = _write_jsonl(NATURAL_TEST, test)
    NATURAL_TEST.chmod(stat.S_IREAD)
    MANIFEST.write_text(
        json.dumps(
            {
                "seed": SPLIT_SEED,
                "source": FRESH_FROZEN.name,
                "dev_file": NATURAL_DEV.name,
                "dev_sha256": h_dev,
                "test_file": NATURAL_TEST.name,
                "test_sha256": h_test,
                "n_dev": len(dev),
                "n_test": len(test),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for name, part in (("dev", dev), ("test", test)):
        counts: dict[str, int] = {}
        for r in part:
            k = f"{r['language']}/{r['type']}"
            counts[k] = counts.get(k, 0) + 1
        print(name, len(part), dict(sorted(counts.items())))


# --------------------------------------------------------------------------- signals
def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _load_kb(embedding_model: str) -> list[dict[str, Any]]:
    factory = get_async_session_factory()
    async with factory() as session:
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.status == "published",
                KnowledgeChunk.is_indexable.is_(True),
                KnowledgeChunk.embedding_model == embedding_model,
            )
        )
        rows = (await session.execute(stmt)).all()
    return [
        {
            "id": str(c.id),
            "title": d.title,
            "heading": c.heading_path or "",
            "text": c.content,
            "embedding": list(c.embedding),
        }
        for c, d in rows
        if c.embedding is not None
    ]


def auroc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """P(score_pos > score_neg) with ties = 0.5."""
    if not pos or not neg:
        return float("nan")
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def choose_operating_point(
    answerable: Sequence[float], other: Sequence[float], far_weight: float = 2.0
) -> dict[str, float]:
    """Pick threshold minimising far_weight*false_answer_rate + false_abstain_rate; median of the optimal plateau."""
    scores = sorted(set(answerable) | set(other))
    cands = [scores[0] - 1e-6] + [(a + b) / 2 for a, b in zip(scores, scores[1:], strict=False)] + [scores[-1] + 1e-6]
    table = []
    for t in cands:
        far = sum(1 for s in other if s >= t) / len(other)
        frr = sum(1 for s in answerable if s < t) / len(answerable)
        table.append((t, far, frr, far_weight * far + frr))
    best = min(c[3] for c in table)
    plateau = sorted(c for c in table if abs(c[3] - best) < 1e-9)
    t, far, frr, _ = plateau[len(plateau) // 2]
    return {"threshold": t, "false_answer_rate": far, "false_abstain_rate": frr, "plateau_size": len(plateau)}


def curve(answerable: Sequence[float], other: Sequence[float], grid: Sequence[float]) -> list[dict[str, float]]:
    return [
        {
            "t": t,
            "false_answer": sum(1 for s in other if s >= t) / len(other),
            "false_abstain": sum(1 for s in answerable if s < t) / len(answerable),
        }
        for t in grid
    ]


async def calibrate(reranker_name: str) -> None:
    from sentence_transformers import CrossEncoder

    cfg = RetrievalConfig()
    embedder = get_embedder()
    kb = await _load_kb(cfg.embedding_model)
    cases = _load_cases(NATURAL_DEV)
    t0 = time.monotonic()
    reranker = CrossEncoder(reranker_name, max_length=512)
    load_s = time.monotonic() - t0

    recs: list[dict[str, Any]] = []
    rerank_ms: list[float] = []
    for c in cases:
        q_vec = embedder.embed_query(c["question"])
        ranked = sorted(kb, key=lambda ch: -float(cosine_similarity(q_vec, ch["embedding"])))[:5]
        cos = [float(cosine_similarity(q_vec, ch["embedding"])) for ch in ranked]
        pairs = [(c["question"], f"{ch['title']} | {ch['heading']}\n{ch['text'][:1500]}") for ch in ranked]
        t1 = time.monotonic()
        raw = [float(x) for x in reranker.predict(pairs)]
        rerank_ms.append((time.monotonic() - t1) * 1000.0)
        recs.append(
            {
                "id": c["id"],
                "language": c["language"],
                "type": c["type"],
                "question": c["question"],
                "cosine": cos[0],
                "rerank_max": max(raw),
                "rerank_sigmoid": 1.0 / (1.0 + math.exp(-max(raw))),
                "top3": [(ch["title"], ch["heading"], round(s, 4)) for ch, s in zip(ranked[:3], cos[:3], strict=False)],
            }
        )

    ans = [r for r in recs if r["type"] == "answerable"]
    oth = [r for r in recs if r["type"] != "answerable"]
    out: dict[str, Any] = {
        "reranker": reranker_name,
        "load_seconds": round(load_s, 2),
        "rerank_ms_median_5pairs": round(statistics.median(rerank_ms), 1),
        "rerank_ms_p95_5pairs": round(sorted(rerank_ms)[int(0.95 * (len(rerank_ms) - 1))], 1),
        "n_answerable": len(ans),
        "n_not_answerable": len(oth),
    }
    lo = min(r["cosine"] for r in recs)
    hi = max(r["cosine"] for r in recs)
    for r in recs:
        r["combined"] = 0.5 * ((r["cosine"] - lo) / (hi - lo)) + 0.5 * r["rerank_sigmoid"]
    for sig in ("cosine", "rerank_sigmoid", "combined"):
        a = [r[sig] for r in ans]
        o = [r[sig] for r in oth]
        out[sig] = {"auroc": round(auroc(a, o), 4), "operating_point": choose_operating_point(a, o)}
        out[sig]["answerable_range"] = [round(min(a), 4), round(max(a), 4)]
        out[sig]["not_answerable_range"] = [round(min(o), 4), round(max(o), 4)]
    out["records"] = recs
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload_dev = json.dumps(out, ensure_ascii=False, indent=1)
    (REPORTS_DIR / "natural_dev_signals.json").write_text(payload_dev, encoding="utf-8")

    print(json.dumps({k: v for k, v in out.items() if k != "records"}, indent=1))
    print("\nTop-3 chunks for every unanswerable dev case (cosine to question):")
    for r in recs:
        if r["type"] == "unanswerable":
            q_line = (
                f"- [{r['id']}] ({r['language']}) cos={r['cosine']:.3f} "
                f"rerank={r['rerank_sigmoid']:.3f} Q: {r['question']}"
            )
            print(q_line)
            for title, heading, s in r["top3"]:
                print(f"    {s:.3f}  {title} > {heading}")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        for ax, sig in zip(axes, ("cosine", "rerank_sigmoid", "combined"), strict=False):
            a = [r[sig] for r in ans]
            o = [r[sig] for r in oth]
            grid = sorted(set(a + o))
            cv = curve(a, o, grid)
            ax.plot(grid, [p["false_answer"] for p in cv], label="false-answer (non-answerable answered)")
            ax.plot(grid, [p["false_abstain"] for p in cv], label="false-abstain (answerable withheld)")
            ax.axvline(out[sig]["operating_point"]["threshold"], color="grey", ls="--")
            ax.set_title(f"{sig} (AUROC {out[sig]['auroc']:.2f}, n={len(recs)})")
            ax.set_xlabel("threshold")
        axes[0].legend(fontsize=7)
        out_png = Path("../docs/ai/abstention_curves.png")
        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(out_png, dpi=110)
        print("plot:", out_png.resolve())
    except Exception as e:  # plotting is optional
        print("plot skipped:", type(e).__name__, e)


# --------------------------------------------------------------------------- guard margin
async def sweep_margin(threshold: float) -> None:
    cfg = RetrievalConfig()
    embedder = get_embedder()
    kb = await _load_kb(cfg.embedding_model)
    guard = PolicyGuard(embedder=embedder)
    cases = _load_cases(NATURAL_DEV)
    pre = []
    for c in cases:
        q_vec = embedder.embed_query(c["question"])
        top = max(float(cosine_similarity(q_vec, ch["embedding"])) for ch in kb)
        pre.append((c, top))
    rows: list[dict[str, Any]] = []
    for m in [round(-0.03 + 0.01 * i, 2) for i in range(12)]:
        fr = sum(
            1 for c, top in pre
            if c["type"] == "answerable" and guard.check(c["question"], kb_sim=top, margin=m).refused
        )
        n_ans = sum(1 for c, _ in pre if c["type"] == "answerable")
        unans_ref = sum(
            1 for c, top in pre
            if c["type"] == "unanswerable" and guard.check(c["question"], kb_sim=top, margin=m).refused
        )
        n_un = sum(1 for c, _ in pre if c["type"] == "unanswerable")
        rec = sum(
            1 for c, top in pre
            if c["type"] == "refusal_expected" and guard.check(c["question"], kb_sim=top, margin=m).refused
        )
        n_rf = sum(1 for c, _ in pre if c["type"] == "refusal_expected")
        rows.append(
            {
                "margin": m,
                "false_refusal_answerable": f"{fr}/{n_ans}",
                "refused_unanswerable": f"{unans_ref}/{n_un}",
                "refusal_recall": f"{rec}/{n_rf}",
                "_fr": fr,
                "_rec": rec,
            }
        )
    feasible = [r for r in rows if r["_fr"] == 0]
    best_rec = max((r["_rec"] for r in feasible), default=0)
    plateau = [r for r in feasible if r["_rec"] == best_rec]
    chosen = plateau[len(plateau) // 2]["margin"]
    for r in rows:
        r.pop("_fr")
        r.pop("_rec")
        print(r)
    print("chosen margin:", chosen, "(zero false refusals on answerable, max recall, median of plateau)")


# --------------------------------------------------------------------------- frozen test
def _fact_hits(chunk_text: str, facts: Sequence[str]) -> int:
    low = chunk_text.lower()
    return sum(1 for f in facts if f.lower() in low)


async def run_frozen_test(threshold: float, retriever_signal: str = "cosine") -> None:
    """Evaluate the frozen natural test split exactly once (fake provider, real embedder)."""
    out_path = REPORTS_DIR / "natural_test_run.json"
    if out_path.exists():
        raise SystemExit(f"Frozen test already evaluated ({out_path}). It must be run only once.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload = NATURAL_TEST.read_text(encoding="utf-8")
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != manifest["test_sha256"]:
        raise SystemExit("Frozen test file hash mismatch; refusing to evaluate.")
    cases = [json.loads(line) for line in payload.splitlines() if line.strip()]

    contacts: list[str] = ["1930", "112", "14448"]
    for item in get_all_verified_contacts():
        for k in ("toll_free_number", "alternate_number", "website"):
            if item.get(k):
                contacts.append(str(item[k]))
                contacts.extend(re.findall(r"\b\d+\b", str(item[k])))

    embedder = get_embedder()
    gateway = LLMGateway(config=LLMConfig(provider="fake", approved_for_real_data=True), adapter=FakeProvider())
    cfg = RetrievalConfig(vector_candidates=20, keyword_candidates=0, return_size=5, min_evidence_score=threshold)
    results: list[dict[str, Any]] = []
    factory = get_async_session_factory()
    async with factory() as session:
        user = await get_or_create_eval_user(session)
        retriever = HybridRetriever(session=session, embedder=embedder, config=cfg)
        service = KnowledgeAnswerService(session=session, retriever=retriever, gateway=gateway)
        for c in cases:
            t0 = time.monotonic()
            evidence = await retriever.retrieve(c["question"])
            retr_ms = (time.monotonic() - t0) * 1000.0
            texts = [ch.text for ch in evidence.chunks]
            t1 = time.monotonic()
            req = KnowledgeQuestionRequest(question=c["question"], language_hint=c["language"])
            resp = await service.answer(req, user)
            ans_ms = (time.monotonic() - t1) * 1000.0
            facts = c.get("required_facts") or []
            need = max(1, math.ceil(len(facts) / 2)) if facts else 0
            rank = next((i for i, t in enumerate(texts, 1) if need and _fact_hits(t, facts) >= need), None)
            retrieved_ids = {ch.chunk_id for ch in evidence.chunks}
            cites = resp.citations
            cit_valid = (
                all(x.chunk_id in retrieved_ids for x in cites) if cites else (resp.status != "answered")
            )
            invented = any(
                v not in contacts and not any(v in t for t in texts) for v in extract_contacts_and_urls(resp.answer)
            )
            grounded = all(
                n in resp.answer and (any(n in t for t in texts) or n in c["question"] or n in ("1930", "112"))
                for n in extract_numbers(resp.answer)
            )
            expected_status = {
                "answerable": "answered",
                "refusal_expected": "refused",
            }.get(c["type"], "insufficient_evidence")
            results.append(
                {
                    "id": c["id"],
                    "language": c["language"],
                    "type": c["type"],
                    "expected": expected_status,
                    "predicted": resp.status,
                    "top_cosine": evidence.top_vector_score,
                    "proxy_hit": rank is not None,
                    "proxy_rr": (1.0 / rank) if rank else 0.0,
                    "fact_cov_answer": (
                        sum(1 for f in facts if f.lower() in resp.answer.lower()) / len(facts) if facts else None
                    ),
                    "citation_valid": cit_valid,
                    "invented_contact": invented,
                    "numeric_grounded": grounded,
                    "retrieval_ms": retr_ms,
                    "answer_ms": ans_ms,
                }
            )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_dict = {"threshold": threshold, "signal": retriever_signal, "provider": "fake", "results": results}
    out_path.write_text(json.dumps(report_dict, ensure_ascii=False, indent=1), encoding="utf-8")
    print(render_test_tables(results))


def _fmt(values: Sequence[float], pct: bool = True) -> str:
    if not values:
        return "n/a (n=0)"
    s = summarize_metric([float(v) for v in values])
    scale = 100.0 if pct else 1.0
    flag = " *" if len(values) < 30 else ""
    low_str = f"{s.ci_95_low * scale:.1f}"
    high_str = f"{s.ci_95_high * scale:.1f}"
    unit = "%" if pct else ""
    return f"{s.mean * scale:.1f}{unit} [{low_str}, {high_str}] n={len(values)}{flag}"


def render_test_tables(results: Sequence[dict[str, Any]]) -> str:
    lines = ["(* = n<30, indicative)"]

    def block(title: str, rows: Sequence[dict[str, Any]]) -> None:
        ans = [r for r in rows if r["type"] == "answerable"]
        una = [r for r in rows if r["type"] == "unanswerable"]
        ref = [r for r in rows if r["type"] == "refusal_expected"]
        answered = [r for r in rows if r["predicted"] == "answered"]
        lines.append(f"\n## {title} (n={len(rows)})")
        lines.append(f"- status accuracy: {_fmt([r['expected'] == r['predicted'] for r in rows])}")
        lines.append(f"- proxy answer-bearing hit@5 (answerable): {_fmt([r['proxy_hit'] for r in ans])}")
        lines.append(f"- proxy MRR (answerable): {_fmt([r['proxy_rr'] for r in ans], pct=False)}")
        fa_msg = _fmt([r['predicted'] == 'insufficient_evidence' for r in ans])
        lines.append(f"- false-abstain (answerable -> insufficient): {fa_msg}")
        fr_msg = _fmt([r['predicted'] == 'refused' for r in ans + una])
        lines.append(f"- false-refusal (answerable/unanswerable -> refused): {fr_msg}")
        lines.append(f"- false-answer (unanswerable answered): {_fmt([r['predicted'] == 'answered' for r in una])}")
        ua_msg = _fmt([r['predicted'] == 'answered' for r in ref])
        lines.append(f"- unsafe-answer (refusal-expected answered): {ua_msg}")
        lines.append(f"- citation validity (answered): {_fmt([r['citation_valid'] for r in answered])}")
        lines.append(f"- invented contacts (all): {_fmt([r['invented_contact'] for r in rows])}")
        lines.append(f"- numeric grounding (all): {_fmt([r['numeric_grounded'] for r in rows])}")
        lines.append(f"- retrieval latency ms: {_fmt([r['retrieval_ms'] for r in rows], pct=False)}")
        lines.append(f"- end-to-end answer latency ms: {_fmt([r['answer_ms'] for r in rows], pct=False)}")

    block("Overall", results)
    for lang in sorted({r["language"] for r in results}):
        block(f"Language: {lang}", [r for r in results if r["language"] == lang])
    for typ in sorted({r["type"] for r in results}):
        block(f"Type: {typ}", [r for r in results if r["type"] == typ])
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("split")
    c = sub.add_parser("calibrate")
    c.add_argument("--reranker", default=RERANKER_DEFAULT)
    m = sub.add_parser("margin")
    m.add_argument("--threshold", type=float, default=0.85)
    t = sub.add_parser("test")
    t.add_argument("--threshold", type=float, required=True)
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if a.cmd == "split":
        do_split()
    elif a.cmd == "calibrate":
        asyncio.run(calibrate(a.reranker))
    elif a.cmd == "margin":
        asyncio.run(sweep_margin(a.threshold))
    else:
        asyncio.run(run_frozen_test(a.threshold))


if __name__ == "__main__":
    main()
