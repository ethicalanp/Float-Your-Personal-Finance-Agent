# ADR-003: Optional Post-Retrieval Cross-Encoder Reranker

- **Status**: Accepted
- **Date**: 2026-11-22
- **Area**: RAG / Retrieval Pipeline

---

## Context

In RAG pipelines, initial hybrid retrieval (dense vector cosine search + sparse keyword search) returns a candidate set of top-$N$ chunks (typically $N = 15$ to $25$). 

A second-stage cross-encoder reranker (such as `BAAI/bge-reranker-v2-m3` or a lightweight distilled cross-encoder like FlashRank) evaluates query-passage pairs jointly with cross-attention. This can significantly improve precision@k, but introduces substantial computational overhead, additional memory footprint, and query latency (adding 50ms–250ms per query depending on hardware).

---

## Decision

**Make the Reranker strictly optional and feature-flagged.** The default RAG pipeline will execute hybrid retrieval with Reciprocal Rank Fusion (RRF) and can function with or without a reranker component.

### Architecture Contract:
1. `BaseReranker` interface defined in `app/ai/rag/reranker.py`.
2. A Null/Pass-through implementation (`NoOpReranker`) is used when `PFA_AI_RERANKER_ENABLED=false` (default).
3. When enabled (`PFA_AI_RERANKER_ENABLED=true`), candidates from hybrid RRF are scored and reordered before trimming to final top-$k$ context (e.g. $k = 4$).

---

## Options Considered

| Strategy | Latency Impact | Multilingual Accuracy | Hardware Requirement | Operational Complexity |
| :--- | :--- | :--- | :--- | :--- |
| **Option A: No Reranker (Pure RRF)** | 0 ms | Good when dense + sparse are complementary | Minimal (standard DB query) | Low |
| **Option B: Heavy Cross-Encoder (`bge-reranker-v2-m3`)** | +120ms to 350ms | Very high (deep cross-attention) | Requires GPU or multi-core CPU with PyTorch | High |
| **Option C: Lightweight Distilled Cross-Encoder (FlashRank / MiniLM)** | +25ms to 50ms | Moderate on English, weaker on Malayalam/Manglish | Pure CPU (ONNX / quantized) | Medium |

---

## Decision Rule & Phase 2 Gate

The decision to enable a reranker in production will be made **only after measuring retrieval quality and latency with and without it** in Phase 2:
- Measure **NDCG@3** and **Precision@3** on the curated bilingual evaluation benchmark.
- Measure p95 search latency.
- If dense vector + RRF achieves satisfactory NDCG@3 (> 0.85) without a reranker, the system will keep the reranker disabled to maximize throughput and minimize resource consumption.
