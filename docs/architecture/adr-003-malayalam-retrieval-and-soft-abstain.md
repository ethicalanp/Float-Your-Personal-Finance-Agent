# ADR-003: Per-Language Retrieval Thresholds and Soft Abstain

- **Status**: Accepted
- **Date**: 2026-11-27

## Context
Baseline `intfloat/multilingual-e5-base` with a single `0.83` cosine threshold produced `100.0% (11/11*)` false abstentions on Malayalam (`ml`) queries on the v2 DEV split (`N=60`), even though `Recall@5` was `90.9% (10/11*)`. Meanwhile, hard empty abstentions on borderline matches withheld useful cited regulatory context.

## Decision
1. **Per-language `min_evidence_score` thresholds** in `RetrievalConfig`: `en=0.83`, `ml=0.79`, `manglish=0.82`.
   - Selected over query-translation (`exp_a`: 12.1% false-abstain + extra LLM latency), curated `ml` chunks alone (`exp_b`: 42.4% false-abstain), combined `a+b+c` (elevated false-answer 22.2% and unsafe-answer 11.1%), and `BAAI/bge-m3` (`exp_d`: 100% Recall@5 but requires 1024-dim pgvector schema migration and ~2.2 GB model footprint).
2. **Soft abstain for borderline confidence** (`soft_abstain_min_score=0.76 <= top_score < threshold`):
   - Returns `status="insufficient_evidence"`, `soft_abstain=True`, grounded excerpts with `[E1]`/`[E2]` citations, and 2 related questions (`related_questions`), while keeping `PolicyGuard` hard refusals (`status="refused"`) unchanged.

## Consequences
- On the one-shot held-out frozen test (`N=60`, SHA-256 `a9a22b33...e00a90`), overall false-abstain is `12.1% (4/33)` (`ml`: `18.2% (2/11*)`, `manglish`: `9.1% (1/11*)`), `Recall@5` is `90.9% (30/33)`, and unsafe-answer is `0.0% (0/9*)`.
- No database migration is required; `BAAI/bge-m3` remains a future option if a 1024-dim migration is scheduled.
- Native Malayalam speaker review is still required for `evals/review/rag_v2_review.csv` (`needs_native_review=True`).
