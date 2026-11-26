# ADR-006: Vector-Only Retrieval Strategy for Multilingual Regulatory Knowledge

- **Status**: Accepted
- **Date**: 2026-11-24
- **Area**: RAG / Retrieval Architecture

---

## Context

Float's Knowledge Assistant answers regulatory compliance, scam defense, and borrowing guidelines across English, Malayalam, and Manglish. The initial architecture planned a hybrid retrieval pipeline combining dense vector cosine similarity (via `intfloat/multilingual-e5-base`, 768 dimensions) with sparse full-text keyword search fused using Reciprocal Rank Fusion (RRF, $k=60$) and an optional lexical cross-reranker.

During Phase 2 systematic evaluation across the 91-case dev split of the curated multilingual benchmark (`rag_dataset_frozen.jsonl`), retrieval performance was measured with rigorous 95% confidence intervals (Wilson score intervals for proportions, 1000-sample bootstrap for continuous metrics).

---

## Benchmark Results (Dev Split, n=49 Answerable Cases)

| Retrieval Mode | Recall@5 (95% CI) | MRR (95% CI) | nDCG@5 (95% CI) | Status Accuracy | p50 Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Vector-Only** | **0.8980** [0.7824, 0.9556] | **0.8776** [0.7857, 0.9592] | **0.8829** [0.7937, 0.9592] | **0.8352** | 303.1 ms |
| **Keyword-Only** | **0.3673** [0.2467, 0.5073] | **0.2653** [0.1612, 0.3842] | **0.2920** [0.1873, 0.4078] | **0.2967** | 260.7 ms |
| **Hybrid (RRF k=60)** | **0.5918** [0.4525, 0.7178] | **0.4694** [0.3421, 0.6014] | **0.5015** [0.3752, 0.6288] | **0.8352** | 363.7 ms |
| **Hybrid + Reranker** | **0.5918** [0.4525, 0.7178] | **0.5204** [0.3891, 0.6512] | **0.5391** [0.4102, 0.6653] | **0.8352** | 347.1 ms |

*(Note: Under multi-gold equivalent chunk matching, Vector-Only Answer-Bearing Hit@5 reaches 1.0000 [0.9275, 1.0000]).*

### Root Cause Analysis:
1. **Agglutinative Morphology**: Malayalam is heavily agglutinative and morphologically rich. Word stems change under case suffixes and verb tenses (e.g., *നിക്ഷേപം*, *നിക്ഷേപിച്ചാൽ*, *നിക്ഷേപിക്കാൻ*). Standard keyword tokenizers (`simple` or `english` FTS) fail to stem Indic words, yielding poor keyword recall (0.3673).
2. **RRF Rank Depression**: Reciprocal Rank Fusion weights vector hits ($1 / (k + r_v)$) and keyword hits ($1 / (k + r_k)$) equally. When keyword search misses or matches irrelevant documents sharing common stopwords, high-quality vector rank-1 hits are depressed below irrelevant chunks that received weak hits from both sources, dropping recall by over 30% absolute (from 89.8% to 59.2%).
3. **Operational Overhead**: Hybrid search executes dual database queries, RRF normalization, and reranking, increasing p50 latency from 303ms to 364ms with no accuracy benefit.

---

## Decision

**Adopt Vector-Only retrieval as Float's primary RAG retrieval strategy.**
1. The default pipeline bypasses sparse keyword search and executes pgvector cosine similarity search (`vector_cosine_ops`) over `knowledge_chunks`.
2. Heading path and document title are prepended to embedded chunk text (`"passage: {doc.title} > {chunk.heading_path}\n{chunk.content}"`), which ensures structural context is embedded directly into the 768-dimensional vector.
3. Dense vector cosine similarity serves as the primary evidence score for the pre-LLM abstention gate (calibrated threshold $\tau = 0.85$).

---

## Conditions to Revisit

Hybrid retrieval or sparse indexing may be reintroduced only under the following specific triggers:
1. **Large Knowledge Base Expansion (> 10,000 chunks)**: If scaling to tens of thousands of regulatory circulars where dense embeddings experience dense collision on specific alphanumeric codes (e.g., exact RBI circular numbers like `DOR.CRE.REC.42/21.04.048/2023-24` or specific bank IFSC codes).
2. **Dedicated Indic Trigram Indexing**: If a dedicated PostgreSQL trigram (`pg_trgm`) index with sub-word character n-gram tokenization tuned specifically for Malayalam and Manglish morphology demonstrates statistically significant improvements over vector-only retrieval on the frozen test split.
