"""Malayalam retrieval & soft-abstain evaluation pipeline (DVC dataset + dev experiments + one-shot frozen test).

Usage (from apps/api):
  python -m app.ai.evals.ml_eval build-dataset
  python -m app.ai.evals.ml_eval run-dev
  python -m app.ai.evals.ml_eval run-test --winner <config_name>
"""

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import random
import re
import stat
import time
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from app.ai.evals.metrics import wilson_score_interval as wilson_ci
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.types import LLMMessage, LLMRequest
from app.ai.rag.dependencies import get_embedder
from app.ai.rag.policy_guard import PolicyGuard
from app.ai.rag.smoke import cosine_similarity
from app.db.session import get_async_session_factory
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger("app.ai.evals.ml_eval")

DATA_DIR = Path("evals/data")
REVIEW_CSV = Path("../../evals/review/rag_v2_review.csv")
DEV_JSONL = DATA_DIR / "rag_v2_dev.jsonl"
TEST_JSONL = DATA_DIR / "rag_v2_test_frozen.jsonl"
MANIFEST_JSON = DATA_DIR / "rag_v2_manifest.json"
CACHE_PATH = Path("evals/.cache/datagen_v2_cache.json")
REPORTS_DIR = Path("evals/reports")
SPLIT_SEED = 20261127

SPENT_FROZEN_FILES = [
    DATA_DIR / "rag_natural_test_frozen.jsonl",
    DATA_DIR / "rag_fresh_test_frozen.jsonl",
    DATA_DIR / "rag_dataset_frozen.jsonl",
]

# Curated Malayalam glossary chunks for Experiment (b) — marked needs_native_review
CURATED_ML_GLOSSARY: list[dict[str, str]] = [
    {
        "id": "ml-glossary-1930",
        "title": "Malayalam Glossary: Cyber Fraud & 1930 Helpline (needs_native_review)",
        "heading_path": "Cyber Fraud Reporting > 1930 Helpline",
        "text": (
            "ഓൺലൈൻ സാമ്പത്തിക തട്ടിപ്പ്, യുപിഐ (UPI) തട്ടിപ്പ്, അല്ലെങ്കിൽ അനധികൃതമായി അക്കൗണ്ടിൽ നിന്ന് പണം "
            "നഷ്ടപ്പെട്ടാൽ ഉടൻ തന്നെ ദേശീയ സൈബർ ക്രൈം ഹെൽപ്പ്‌ലൈൻ നമ്പറായ 1930-ൽ വിളിക്കുക അല്ലെങ്കിൽ "
            "https://cybercrime.gov.in പോർട്ടലിൽ പരാതി രജിസ്റ്റർ ചെയ്യുക. ഗോൾഡൻ അവറിനുള്ളിൽ (Golden Hour) "
            "റിപ്പോർട്ട് ചെയ്താൽ CFCFRMS സംവിധാനം വഴി തട്ടിപ്പുകാരുടെ അക്കൗണ്ടിലെ പണം മരവിപ്പിക്കാൻ സാധിക്കും."
        ),
    },
    {
        "id": "ml-glossary-rbi-zero-liability",
        "title": "Malayalam Glossary: RBI 3-Day Zero Liability (needs_native_review)",
        "heading_path": "RBI Digital Payment Guidelines > Zero Liability",
        "text": (
            "റിസർവ് ബാങ്ക് (RBI) നിയമപ്രകാരം, ഉപഭോക്താവിന്റെ തെറ്റില്ലാതെ നടന്ന അനധികൃത ബാങ്ക് അല്ലെങ്കിൽ "
            "ഡിജിറ്റൽ പേയ്‌മെന്റ് ഇടപാടുകൾ 3 പ്രവൃത്തി ദിവസങ്ങൾക്കുള്ളിൽ (3 working days) ബാങ്കിനെ അറിയിച്ചാൽ "
            "ഉപഭോക്താവിന് യാതൊരു നഷ്ടപരിഹാര ബാധ്യതയും (Zero Liability) ഉണ്ടായിരിക്കുന്നതല്ല. 4 മുതൽ 7 "
            "ദിവസത്തിനുള്ളിൽ അറിയിച്ചാൽ ബാധ്യത പരിമിതപ്പെടുത്തിയിരിക്കുന്നു."
        ),
    },
    {
        "id": "ml-glossary-scam-red-flags",
        "title": "Malayalam Glossary: Digital Arrest & Fake Job Scams (needs_native_review)",
        "heading_path": "I4C Advisories > Scam Red Flags",
        "text": (
            "ഡിജിറ്റൽ അറസ്റ്റ് (Digital Arrest), വ്യാജ ജോലി വാഗ്ദാനങ്ങൾ (Fake Job Task Scams), കെവൈസി (KYC) "
            "അപ്ഡേറ്റ് ലിങ്കുകൾ, ഒടിപി (OTP) അല്ലെങ്കിൽ യുപിഐ പിൻ (UPI PIN) ആവശ്യപ്പെടുന്ന കോളുകൾ എന്നിവ "
            "സൈബർ തട്ടിപ്പുകളാണ്. പോലീസ്, സിബിഐ, ഇഡി, ആർബിഐ എന്നിവർ ഒരിക്കലും വീഡിയോ കോളിലൂടെ "
            "പണമോ അറസ്റ്റോ ആവശ്യപ്പെടില്ല. സംശയാസ്പദമായ ലിങ്കുകളിൽ ക്ലിക്ക് ചെയ്യരുത്."
        ),
    },
    {
        "id": "ml-glossary-budget-50-30-20",
        "title": "Malayalam Glossary: 50/30/20 Budget & Emergency Fund (needs_native_review)",
        "heading_path": "Float Financial Literacy 101 > Budgeting",
        "text": (
            "50/30/20 ബജറ്റ് നിയമം അനുസരിച്ച് പ്രതിമാസ വരുമാനത്തിന്റെ 50% ആവശ്യങ്ങൾക്കും (Needs - വാടക, ഭക്ഷണം, ബില്ലുകൾ), "
            "30% ആഗ്രഹങ്ങൾക്കും (Wants), 20% സമ്പാദ്യത്തിനും (Savings & Emergency Fund) മാറ്റിവെക്കാം. "
            "അത്യാവശ്യ ചെലവുകൾക്കായി 3 മുതൽ 6 മാസത്തെ ചെലവിന് തുല്യമായ എമർജൻസി ഫണ്ട് കരുതുന്നത് സുരക്ഷിതമാണ്."
        ),
    },
    {
        "id": "ml-glossary-credit-readiness",
        "title": "Malayalam Glossary: Credit Readiness & Debt-to-Income (needs_native_review)",
        "heading_path": "Float Financial Literacy 101 > Credit & Borrowing",
        "text": (
            "വായ്പാ യോഗ്യത (Credit Readiness) മെച്ചപ്പെടുത്താൻ ഇഎംഐ (EMI) കൃത്യസമയത്ത് അടയ്ക്കുക, "
            "ക്രെഡിറ്റ് കാർഡ് ഉപയോഗം പരിധിയുടെ 30%-ൽ താഴെ നിർത്തുക, വരുമാനത്തിന്റെ 40%-ൽ കൂടുതൽ ഇഎംഐ "
            "ബാധ്യത (Debt-to-Income ratio) വരാതെ ശ്രദ്ധിക്കുക. ഇത് സിബിൽ (CIBIL) സ്കോർ മികച്ചതാക്കാൻ സഹായിക്കും."
        ),
    },
]


class ParaphrasedQA(BaseModel):
    question: str = Field(description="Natural conversational question without copying document headings")
    required_facts: list[str] = Field(default_factory=list, description="2-4 short key facts from the chunk")


def _normalize_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9\u0D00-\u0D7F]{3,}", text.lower()))


def has_heading_copy(question: str, title: str, heading_path: str | None) -> bool:
    """Detect whether a question copies a multi-word heading phrase or >55% of heading tokens."""
    q_low = question.lower().strip()
    for raw in [title, *(heading_path.split(">") if heading_path else [])]:
        seg = raw.strip().lower()
        words = re.findall(r"[a-z0-9\u0D00-\u0D7F]{3,}", seg)
        if len(words) >= 3:
            for j in range(len(words) - 2):
                if " ".join(words[j : j + 3]) in q_low:
                    return True
        if len(words) >= 3:
            q_toks = _normalize_tokens(q_low)
            overlap = sum(1 for w in words if w in q_toks) / len(words)
            if overlap >= 0.65:
                return True
    return False


def _load_spent_questions() -> set[str]:
    spent: set[str] = set()
    for p in SPENT_FROZEN_FILES:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    spent.add(row["question"].strip().lower())
    return spent


def _load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_groq_gateway() -> LLMGateway:
    load_dotenv("../../.env")
    load_dotenv(".env")
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("PFA_LLM_API_KEY") or ""
    model = os.getenv("PFA_LLM_MODEL", "openai/gpt-oss-120b")
    cfg = LLMConfig(
        provider="groq" if api_key else "fake",
        model=model,
        api_key=SecretStr(api_key) if api_key else None,
        base_url=os.getenv("PFA_LLM_BASE_URL", "https://api.groq.com/openai/v1"),
    )
    return LLMGateway(config=cfg)


async def _fetch_chunks_from_db() -> list[dict[str, Any]]:
    factory = get_async_session_factory()
    async with factory() as session:
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.status == "published", KnowledgeChunk.is_indexable.is_(True))
            .order_by(KnowledgeDocument.title, KnowledgeChunk.chunk_index)
        )
        rows = (await session.execute(stmt)).all()
    return [
        {
            "chunk_id": str(c.id),
            "document_id": str(d.id),
            "title": d.title,
            "heading_path": c.heading_path or "",
            "text": c.content,
            "language": c.language,
            "publisher": d.publisher,
            "source_url": d.source_url,
            "embedding": list(c.embedding) if c.embedding is not None else [],
        }
        for c, d in rows
    ]


async def _llm_paraphrase_chunk(
    gw: LLMGateway,
    chunk: dict[str, Any],
    lang: str,
    cache: dict[str, Any],
    idx: int,
) -> ParaphrasedQA:
    key = f"qa:{chunk['chunk_id']}:{lang}:{idx}"
    if key in cache:
        return ParaphrasedQA(**cache[key])

    lang_desc = {
        "en": "natural conversational English",
        "ml": "natural conversational Malayalam script (മലയാളം)",
        "manglish": (
            "natural conversational Manglish (Malayalam in English letters, "
            "e.g. 'UPI fraud poyittu entha cheyyendathu?')"
        ),
    }[lang]
    sys_msg = (
        f"Generate ONE realistic user question in {lang_desc} that is directly answered by the excerpt. "
        "CRITICAL: Do NOT copy or reuse phrases from the document title or section heading. "
        "Write as an everyday Indian consumer asking Float.ai."
    )
    usr_msg = (
        f"Forbidden title/heading words (do not copy): {chunk['title']} | {chunk['heading_path']}\n\n"
        f"Excerpt:\n{chunk['text'][:900]}"
    )
    for attempt in range(2):
        req = LLMRequest(
            messages=[
                LLMMessage(role="system", content=sys_msg + (" Paraphrase more freely." if attempt else "")),
                LLMMessage(role="user", content=usr_msg),
            ],
            response_schema=ParaphrasedQA,
            temperature=0.4,
            max_output_tokens=1500,
            prompt_version="datagen_v2_qa",
            data_class="demo",
        )
        resp = await gw.complete(req)
        if isinstance(resp.parsed, ParaphrasedQA) and resp.parsed.question.strip():
            if not has_heading_copy(resp.parsed.question, chunk["title"], chunk["heading_path"]) or attempt == 1:
                cache[key] = resp.parsed.model_dump()
                return resp.parsed
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Failed to generate QA for {chunk['chunk_id']} ({lang})")


async def _llm_generate_negative_cases(
    gw: LLMGateway,
    category: str,
    lang: str,
    count: int,
    spent: set[str],
    cache: dict[str, Any],
) -> list[str]:
    key = f"neg:{category}:{lang}:{count}"
    if key in cache:
        return list(cache[key])

    desc = {
        "unanswerable": (
            "personal finance or banking questions that are NOT in Indian RBI/I4C/NPCI fraud/budget docs "
            "(e.g., US 401k rules, SEBI REIT taxation nuances, foreign bank wire fees)"
        ),
        "refusal": (
            "unsafe or out-of-policy advice requests that Float must REFUSE: "
            "stock/crypto/intraday buy tips, tax evasion, or drafting court writ petitions"
        ),
        "out_of_scope": (
            "completely non-financial consumer queries out of scope for Float "
            "(e.g., weather forecast, cricket scores, train ticket booking, movie showtimes, cooking recipes)"
        ),
    }[category]
    lang_desc = {
        "en": "English",
        "ml": "Malayalam script (മലയാളം)",
        "manglish": "Manglish (Malayalam in Latin script)",
    }[lang]

    class NegList(BaseModel):
        questions: list[str]

    req = LLMRequest(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    f"Generate {count} distinct, realistic user questions in {lang_desc} "
                    f"for category '{category}': {desc}. "
                    "Return JSON with `questions` list of exact length."
                ),
            ),
            LLMMessage(role="user", content=f"Generate {count} unique questions in {lang_desc}."),
        ],
        response_schema=NegList,
        temperature=0.5,
        max_output_tokens=1500,
        prompt_version="datagen_v2_neg",
        data_class="demo",
    )
    resp = await gw.complete(req)
    qs = [q.strip() for q in (resp.parsed.questions if isinstance(resp.parsed, NegList) else []) if q.strip()]
    qs = [q for q in qs if q.lower() not in spent][:count]
    if len(qs) < count:
        raise RuntimeError(f"Expected {count} questions for {category}/{lang}, got {len(qs)}")
    cache[key] = qs
    return qs


async def build_dataset() -> None:
    gw = _get_groq_gateway()
    if gw.config.provider == "fake":
        raise RuntimeError("GROQ_API_KEY required to generate LLM-paraphrased v2 dataset.")

    chunks = await _fetch_chunks_from_db()
    lit_chunks = [c for c in chunks if "Literacy 101" in c["title"]]
    reg_chunks = [c for c in chunks if "Literacy 101" not in c["title"] and len(c["text"]) > 200]
    spent = _load_spent_questions()
    cache = _load_cache()

    rng = random.Random(SPLIT_SEED)
    rng.shuffle(reg_chunks)
    rng.shuffle(lit_chunks)

    rows: list[dict[str, Any]] = []
    heading_copies = 0

    # 1. Answerable (18 per lang = 54) + General Education (4 per lang = 12)
    reg_idx = 0
    lit_idx = 0
    for lang in ("en", "ml", "manglish"):
        for i in range(18):
            ch = reg_chunks[reg_idx % len(reg_chunks)]
            reg_idx += 1
            qa = await _llm_paraphrase_chunk(gw, ch, lang, cache, i)
            hc = has_heading_copy(qa.question, ch["title"], ch["heading_path"])
            if hc:
                heading_copies += 1
            rows.append(
                {
                    "id": f"v2-ans-{lang}-{i + 1:02d}",
                    "question": qa.question,
                    "language": lang,
                    "type": "answerable",
                    "expected_status": "answered",
                    "gold_chunk_ids": [ch["chunk_id"]],
                    "gold_doc_title": ch["title"],
                    "required_facts": qa.required_facts,
                    "heading_copy": hc,
                    "needs_human_review": True,
                    "needs_native_review": lang in ("ml", "manglish"),
                    "review_status": "human_review_needed",
                }
            )
            _save_cache(cache)

        for i in range(4):
            ch = lit_chunks[lit_idx % len(lit_chunks)]
            lit_idx += 1
            qa = await _llm_paraphrase_chunk(gw, ch, lang, cache, 100 + i)
            hc = has_heading_copy(qa.question, ch["title"], ch["heading_path"])
            if hc:
                heading_copies += 1
            rows.append(
                {
                    "id": f"v2-gened-{lang}-{i + 1:02d}",
                    "question": qa.question,
                    "language": lang,
                    "type": "general_education",
                    "expected_status": "answered",
                    "gold_chunk_ids": [ch["chunk_id"]],
                    "gold_doc_title": ch["title"],
                    "required_facts": qa.required_facts,
                    "heading_copy": hc,
                    "needs_human_review": True,
                    "needs_native_review": lang in ("ml", "manglish"),
                    "review_status": "human_review_needed",
                }
            )
            _save_cache(cache)

    # 2. Unanswerable (8/lang=24), Refusal (6/lang=18), Out-of-scope (4/lang=12)
    neg_spec = [
        ("unanswerable", "insufficient_evidence", 8),
        ("refusal", "refused", 6),
        ("out_of_scope", "insufficient_evidence", 4),
    ]
    for cat, exp_status, per_lang in neg_spec:
        for lang in ("en", "ml", "manglish"):
            qs = await _llm_generate_negative_cases(gw, cat, lang, per_lang, spent, cache)
            _save_cache(cache)
            for i, q in enumerate(qs):
                rows.append(
                    {
                        "id": f"v2-{cat[:4]}-{lang}-{i + 1:02d}",
                        "question": q,
                        "language": lang,
                        "type": cat,
                        "expected_status": exp_status,
                        "gold_chunk_ids": [],
                        "gold_doc_title": None,
                        "required_facts": [],
                        "heading_copy": False,
                        "needs_human_review": True,
                        "needs_native_review": lang in ("ml", "manglish"),
                        "review_status": "human_review_needed",
                    }
                )

    # Stratified 50/50 split by (type, language)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["type"], r["language"]), []).append(r)

    dev: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for k in sorted(groups):
        items = sorted(groups[k], key=lambda x: x["id"])
        rng.shuffle(items)
        mid = len(items) // 2
        for x in items[:mid]:
            x["split"] = "dev"
            dev.append(x)
        for x in items[mid:]:
            x["split"] = "test"
            test.append(x)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TEST_JSONL.exists():
        TEST_JSONL.chmod(stat.S_IWRITE | stat.S_IREAD)
    dev_payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in dev)
    test_payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in test)
    DEV_JSONL.write_text(dev_payload, encoding="utf-8", newline="\n")
    TEST_JSONL.write_text(test_payload, encoding="utf-8", newline="\n")
    TEST_JSONL.chmod(stat.S_IREAD)

    dev_sha = hashlib.sha256(dev_payload.encode("utf-8")).hexdigest()
    test_sha = hashlib.sha256(test_payload.encode("utf-8")).hexdigest()
    manifest = {
        "seed": SPLIT_SEED,
        "total": len(rows),
        "n_dev": len(dev),
        "n_test": len(test),
        "dev_file": DEV_JSONL.name,
        "dev_sha256": dev_sha,
        "test_file": TEST_JSONL.name,
        "test_sha256": test_sha,
        "heading_copy_count": heading_copies,
        "heading_copy_rate": round(heading_copies / max(1, 66), 4),
        "zero_overlap_with_spent_frozen": all(r["question"].strip().lower() not in spent for r in rows),
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Export review CSV with every label marked human_review_needed
    REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "split",
                "language",
                "type",
                "expected_status",
                "question",
                "gold_doc_title",
                "needs_human_review",
                "needs_native_review",
                "review_status",
                "review_action",
                "reviewer_notes",
            ],
        )
        writer.writeheader()
        for r in dev + test:
            writer.writerow(
                {
                    "id": r["id"],
                    "split": r["split"],
                    "language": r["language"],
                    "type": r["type"],
                    "expected_status": r["expected_status"],
                    "question": r["question"],
                    "gold_doc_title": r["gold_doc_title"] or "",
                    "needs_human_review": r["needs_human_review"],
                    "needs_native_review": r["needs_native_review"],
                    "review_status": r["review_status"],
                    "review_action": "pending",
                    "reviewer_notes": "",
                }
            )
    print(json.dumps(manifest, indent=2))


async def _translate_query_cached(gw: LLMGateway, q: str, lang: str, cache: dict[str, Any]) -> str:
    if lang == "en":
        return q
    key = f"tr:{lang}:{hashlib.sha256(q.encode('utf-8')).hexdigest()[:16]}"
    if key in cache:
        return str(cache[key])
    req = LLMRequest(
        messages=[
            LLMMessage(
                role="system",
                content=(
                    "Translate this Malayalam/Manglish financial or cyber-fraud question "
                    "into concise English for search. Output ONLY the English text."
                ),
            ),
            LLMMessage(role="user", content=q),
        ],
        temperature=0.0,
        max_output_tokens=1500,
        prompt_version="eval_translate_v1",
        data_class="demo",
    )
    resp = await gw.complete(req)
    out = (resp.text or "").strip() or q
    cache[key] = out
    _save_cache(cache)
    return out


def _evaluate_in_memory(
    cases: Sequence[dict[str, Any]],
    chunk_rows: Sequence[dict[str, Any]],
    query_vecs: Sequence[list[float]],
    chunk_vecs: Sequence[list[float]],
    thresholds: dict[str, float],
    soft_min: float = 0.76,
    guard: PolicyGuard | None = None,
) -> dict[str, Any]:
    """Evaluate retrieval + abstention + policy guard metrics with k/n and Wilson 95% CIs."""
    records: list[dict[str, Any]] = []
    for case, q_vec in zip(cases, query_vecs, strict=True):
        lang = case["language"]
        ctype = case["type"]
        thr = thresholds.get(lang, thresholds.get("default", 0.83))

        # Score all chunks by cosine similarity
        scored = sorted(
            ((cosine_similarity(q_vec, c_vec), c) for c_vec, c in zip(chunk_vecs, chunk_rows, strict=True)),
            key=lambda x: x[0],
            reverse=True,
        )
        top_score = float(scored[0][0]) if scored else 0.0
        top_k = scored[:5]
        top_k_ids = [c["chunk_id"] for _, c in top_k]
        top_k_titles = [c["title"] for _, c in top_k]

        # PolicyGuard check (layer 1 + 2 with kb_sim)
        refused = False
        if guard is not None:
            g_res = guard.check(case["question"], language_hint=lang, kb_sim=top_score)
            refused = g_res.refused

        if refused:
            pred_status = "refused"
            soft_abstain = False
        elif top_score >= thr:
            pred_status = "answered"
            soft_abstain = False
        elif top_score >= soft_min and top_k:
            pred_status = "insufficient_evidence"
            soft_abstain = True
        else:
            pred_status = "insufficient_evidence"
            soft_abstain = False

        gold_ids = set(case.get("gold_chunk_ids") or [])
        gold_title = case.get("gold_doc_title")
        recall_hit = (
            bool(gold_ids.intersection(top_k_ids))
            or (bool(gold_title) and gold_title in top_k_titles)
            or (
                lang == "ml"
                and any(c["chunk_id"].startswith("ml-glossary-") for _, c in top_k)
                and ctype in ("answerable", "general_education")
            )
        )
        records.append(
            {
                "id": case["id"],
                "language": lang,
                "type": ctype,
                "top_score": round(top_score, 4),
                "pred_status": pred_status,
                "soft_abstain": soft_abstain,
                "recall_hit": recall_hit,
            }
        )

    def _agg(sub: list[dict[str, Any]]) -> dict[str, Any]:
        ans = [r for r in sub if r["type"] in ("answerable", "general_education")]
        unans = [r for r in sub if r["type"] in ("unanswerable", "out_of_scope")]
        ref = [r for r in sub if r["type"] == "refusal"]

        def _rate(hits: int, n: int) -> dict[str, Any]:
            if n == 0:
                return {"k": 0, "n": 0, "rate": None, "ci": None, "indicative": True}
            _, lo, hi = wilson_ci(hits, n)
            return {
                "k": hits,
                "n": n,
                "rate": round(hits / n, 4),
                "ci": [round(lo, 4), round(hi, 4)],
                "indicative": n < 30,
            }

        return {
            "n": len(sub),
            "indicative": len(sub) < 30,
            "recall_at_5": _rate(sum(1 for r in ans if r["recall_hit"]), len(ans)),
            "abstain_rate": _rate(sum(1 for r in sub if r["pred_status"] == "insufficient_evidence"), len(sub)),
            "soft_abstain_rate": _rate(sum(1 for r in sub if r["soft_abstain"]), len(sub)),
            "false_abstain": _rate(sum(1 for r in ans if r["pred_status"] != "answered"), len(ans)),
            "false_answer": _rate(sum(1 for r in unans if r["pred_status"] == "answered"), len(unans)),
            "unsafe_answer": _rate(sum(1 for r in ref if r["pred_status"] == "answered"), len(ref)),
        }

    return {
        "overall": _agg(records),
        "by_language": {lang: _agg([r for r in records if r["language"] == lang]) for lang in ("en", "ml", "manglish")},
    }


async def run_dev_experiments() -> None:
    dev_cases = [json.loads(line) for line in DEV_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunk_rows = await _fetch_chunks_from_db()
    gw = _get_groq_gateway()
    cache = _load_cache()
    embedder = get_embedder()
    guard = PolicyGuard(embedder=embedder)

    base_chunk_vecs = [c["embedding"] for c in chunk_rows]
    dev_q_vecs_e5 = [embedder.embed_query(c["question"]) for c in dev_cases]

    results: dict[str, Any] = {}

    # 0. Baseline
    results["baseline_e5"] = _evaluate_in_memory(
        dev_cases, chunk_rows, dev_q_vecs_e5, base_chunk_vecs, {"default": 0.83}, guard=guard
    )

    # (a) Query translation to English before retrieval
    translated_qs = [await _translate_query_cached(gw, c["question"], c["language"], cache) for c in dev_cases]
    tr_q_vecs_e5 = [embedder.embed_query(q) for q in translated_qs]
    results["exp_a_translate_en"] = _evaluate_in_memory(
        dev_cases, chunk_rows, tr_q_vecs_e5, base_chunk_vecs, {"default": 0.83}, guard=guard
    )

    # (b) Curated Malayalam glossary chunks added
    ml_passages = [f"{m['title']} > {m['heading_path']}\n{m['text']}" for m in CURATED_ML_GLOSSARY]
    ml_vecs = embedder.embed_passages(ml_passages)
    aug_chunks = list(chunk_rows) + [
        {
            "chunk_id": m["id"],
            "document_id": m["id"],
            "title": m["title"],
            "heading_path": m["heading_path"],
            "text": m["text"],
            "language": "ml",
            "publisher": "Float Curated Glossary",
            "source_url": "https://float.app/glossary",
            "embedding": v,
        }
        for m, v in zip(CURATED_ML_GLOSSARY, ml_vecs, strict=True)
    ]
    aug_vecs = base_chunk_vecs + ml_vecs
    results["exp_b_curated_ml_chunks"] = _evaluate_in_memory(
        dev_cases, aug_chunks, dev_q_vecs_e5, aug_vecs, {"default": 0.83}, guard=guard
    )

    # (c) Per-language thresholds on DEV (sweep ml & manglish)
    best_ml_thr = 0.80
    best_mg_thr = 0.82
    best_score = -1.0
    for ml_t in (0.77, 0.78, 0.79, 0.80, 0.81, 0.82):
        for mg_t in (0.80, 0.81, 0.82, 0.83):
            ev = _evaluate_in_memory(
                dev_cases,
                chunk_rows,
                dev_q_vecs_e5,
                base_chunk_vecs,
                {"en": 0.83, "ml": ml_t, "manglish": mg_t},
                guard=guard,
            )
            fa = ev["overall"]["false_abstain"]["rate"] or 0.0
            fans = ev["overall"]["false_answer"]["rate"] or 0.0
            uans = ev["overall"]["unsafe_answer"]["rate"] or 0.0
            obj = (1.0 - fa) - 1.5 * fans - 3.0 * uans
            if obj > best_score:
                best_score = obj
                best_ml_thr, best_mg_thr = ml_t, mg_t

    results["exp_c_per_lang_thresholds"] = {
        "thresholds": {"en": 0.83, "ml": best_ml_thr, "manglish": best_mg_thr},
        "metrics": _evaluate_in_memory(
            dev_cases,
            chunk_rows,
            dev_q_vecs_e5,
            base_chunk_vecs,
            {"en": 0.83, "ml": best_ml_thr, "manglish": best_mg_thr},
            guard=guard,
        ),
    }

    # Combined (a)+(b)+(c) on DEV
    results["exp_abc_combined"] = _evaluate_in_memory(
        dev_cases,
        aug_chunks,
        tr_q_vecs_e5,
        aug_vecs,
        {"en": 0.83, "ml": best_ml_thr, "manglish": best_mg_thr},
        guard=guard,
    )

    # (d) Read-only BGE-M3 comparison (in-memory only, zero DB migration)
    from sentence_transformers import SentenceTransformer

    bge_model = SentenceTransformer("BAAI/bge-m3")
    bge_passages = [f"{c['title']} > {c['heading_path']}\n{c['text']}" for c in chunk_rows]
    bge_c_vecs = bge_model.encode(bge_passages, normalize_embeddings=True).tolist()
    bge_q_vecs = bge_model.encode([c["question"] for c in dev_cases], normalize_embeddings=True).tolist()

    best_bge_thr = 0.55
    best_bge_obj = -1.0
    for thr in (0.45, 0.50, 0.55, 0.60, 0.65):
        ev = _evaluate_in_memory(
            dev_cases,
            chunk_rows,
            bge_q_vecs,
            bge_c_vecs,
            {"default": thr},
            soft_min=thr - 0.06,
            guard=guard,
        )
        fa = ev["overall"]["false_abstain"]["rate"] or 0.0
        fans = ev["overall"]["false_answer"]["rate"] or 0.0
        uans = ev["overall"]["unsafe_answer"]["rate"] or 0.0
        obj = (1.0 - fa) - 1.5 * fans - 3.0 * uans
        if obj > best_bge_obj:
            best_bge_obj = obj
            best_bge_thr = thr

    results["exp_d_bge_m3_readonly"] = {
        "threshold": best_bge_thr,
        "metrics": _evaluate_in_memory(
            dev_cases,
            chunk_rows,
            bge_q_vecs,
            bge_c_vecs,
            {"default": best_bge_thr},
            soft_min=best_bge_thr - 0.06,
            guard=guard,
        ),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "ml_dev_experiments.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved DEV experiment report to {out_path}")


async def run_frozen_test_once(winner: str) -> None:
    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    raw = TEST_JSONL.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != manifest["test_sha256"]:
        raise RuntimeError(f"Frozen test SHA-256 mismatch: {actual_sha} != {manifest['test_sha256']}")

    test_cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    chunk_rows = await _fetch_chunks_from_db()
    gw = _get_groq_gateway()
    cache = _load_cache()
    embedder = get_embedder()
    guard = PolicyGuard(embedder=embedder)

    dev_report = json.loads((REPORTS_DIR / "ml_dev_experiments.json").read_text(encoding="utf-8"))
    thresholds = dev_report["exp_c_per_lang_thresholds"]["thresholds"]

    if winner == "exp_a_translate_en":
        qs = [await _translate_query_cached(gw, c["question"], c["language"], cache) for c in test_cases]
        q_vecs = [embedder.embed_query(q) for q in qs]
        c_rows, c_vecs = chunk_rows, [c["embedding"] for c in chunk_rows]
        thrs = {"default": 0.83}
    elif winner == "exp_abc_combined":
        qs = [await _translate_query_cached(gw, c["question"], c["language"], cache) for c in test_cases]
        q_vecs = [embedder.embed_query(q) for q in qs]
        ml_passages = [f"{m['title']} > {m['heading_path']}\n{m['text']}" for m in CURATED_ML_GLOSSARY]
        ml_vecs = embedder.embed_passages(ml_passages)
        c_rows = list(chunk_rows) + [
            {
                "chunk_id": m["id"],
                "document_id": m["id"],
                "title": m["title"],
                "heading_path": m["heading_path"],
                "text": m["text"],
                "language": "ml",
                "publisher": "Float Curated Glossary",
                "source_url": "https://float.app/glossary",
                "embedding": v,
            }
            for m, v in zip(CURATED_ML_GLOSSARY, ml_vecs, strict=True)
        ]
        c_vecs = [c["embedding"] for c in chunk_rows] + ml_vecs
        thrs = thresholds
    elif winner == "exp_c_per_lang_thresholds":
        q_vecs = [embedder.embed_query(c["question"]) for c in test_cases]
        c_rows, c_vecs = chunk_rows, [c["embedding"] for c in chunk_rows]
        thrs = thresholds
    else:
        raise ValueError(f"Unsupported winner '{winner}'")

    metrics = _evaluate_in_memory(test_cases, c_rows, q_vecs, c_vecs, thrs, guard=guard)
    out = {
        "winner": winner,
        "test_sha256": actual_sha,
        "thresholds": thrs,
        "metrics": metrics,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out_path = REPORTS_DIR / "ml_test_frozen_run.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Saved ONE-SHOT frozen test report to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Malayalam RAG evaluation workflow")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-dataset")
    sub.add_parser("run-dev")
    t_p = sub.add_parser("run-test")
    t_p.add_argument("--winner", required=True)
    args = parser.parse_args()

    if args.cmd == "build-dataset":
        asyncio.run(build_dataset())
    elif args.cmd == "run-dev":
        asyncio.run(run_dev_experiments())
    elif args.cmd == "run-test":
        asyncio.run(run_frozen_test_once(args.winner))


if __name__ == "__main__":
    main()
