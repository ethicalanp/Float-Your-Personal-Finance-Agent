# ADR-004: Vector Index Strategy and Filtered-ANN Recall Safeguards

- **Status**: Accepted
- **Date**: 2026-11-22
- **Area**: RAG / Database & Vector Search

---

## Context

In `app/models/knowledge.py`, the existing index on `knowledge_chunks.embedding` is defined as:
```python
Index(
    "idx_knowledge_chunks_embedding",
    "embedding",
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
```

### The Filtered-ANN Problem
In Approximate Nearest Neighbor (ANN) index structures such as HNSW or IVFFlat, vector graphs are constructed across all vectors. 
When a query applies strict metadata filters (e.g. `document.publisher = 'RBI'`, `document.version = 'v2'`, or `chunk.language = 'ml'`), pgvector must traverse the graph while filtering nodes:
1. **Disconnected Subgraph Trap**: If filtered vectors are sparsely distributed across the graph, traversal can terminate prematurely at dead ends, causing valid matching documents to be silently dropped (filtered recall drops from 95%+ to under 30%).
2. **Corpus Scale Reality**: Float's curated authoritative financial and fraud guidance corpus (RBI circulars, CERT-In advisories, SEBI guidelines, bank dispute templates, scam indicators) comprises hundreds to a few thousand chunks—not millions.

At a corpus size under a few thousand chunks, an **exact sequential scan** (`ORDER BY embedding <=> query_vector LIMIT k` without relying on approximate graph hops) takes less than **3–8 milliseconds** in PostgreSQL with pgvector, while delivering **100.0% recall guaranteed**, completely immune to filtered-ANN recall collapse.

---

## Decision

1. **Default to Exact Scan for Small Corpus**:
   - For corpus sizes under 10,000 chunks, queries will utilize exact scan (`SET LOCAL enable_indexscan = off;` for the vector index or query shapes that maintain exact scan) whenever strict metadata filters (`status = 'published'`, `language = '...'`, `publisher = '...'`) are present.
2. **HNSW Activation Gate**:
   - Only activate HNSW if the corpus grows significantly (> 50,000 chunks) and p95 retrieval latency exceeds acceptable thresholds (> 35ms).
3. **Mandatory Filtered-ANN Regression Tests**:
   - Implement an automated test in `tests/test_rag_retrieval.py` verifying that queries with multiple metadata filters (`status = 'published'`, `language = 'en'`) retrieve the exact expected ground-truth chunks without silent drops.

---

## Consequences

- Zero risk of silent omission of vital compliance guidelines or helpline procedures due to graph disconnection.
- Sub-10ms query execution across Float's curated knowledge base.
- Transparent migration path as corpus scales.
