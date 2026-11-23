# ADR-001: Multilingual Embedding Model Selection and Dimension Alignment

- **Status**: Accepted
- **Date**: 2026-11-22
- **Area**: RAG / Vector Search

---

## Context

The database schema (`app/models/knowledge.py` and migration `4f3fa7945abe_enable_pgvector_extension.py` / `b3c4d5e6f708_align_schema_with_dbml_v2.py`) defines:
```python
embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
```

Float requires dense retrieval across three key language formats encountered in Indian financial fraud and guidance:
1. **English** (Standard banking terms, RBI circulars, Swiggy/Amazon notifications).
2. **Malayalam** (`ml` script — official KSEB notices, local news, cybercrime alerts).
3. **Hindi** (`hi` script — national bank notifications, Central Government advisories).
4. **Manglish** (Phonetic Malayalam written in Latin script).

We must verify the real output dimension of the candidate multilingual embedding model and either confirm 768 dimensions or specify an Alembic migration.

---

## Options Considered

| Option | Architecture | Dimensions | Multilingual Coverage (EN, ML, HI) | Prefix Requirements | License / Deployment | Schema Compatibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Option A: `intfloat/multilingual-e5-base`** | 12-layer XLM-RoBERTa base | **768** | Excellent (covers 100+ languages including Malayalam & Hindi; top MTEB multilingual benchmark) | **Required**: `"query: "` for queries, `"passage: "` for chunks | MIT (commercial permissible, self-hostable via ONNX / PyTorch / HF) | **Native 768**: 100% match. No DB migration required. |
| **Option B: `BAAI/bge-m3`** | Custom dense+sparse multi-ling | **1024** | Outstanding for Indo-Aryan and Dravidian scripts | None required | Apache 2.0 | **Mismatch**: Requires `ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1024)`. |
| **Option C: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`** | 12-layer XLM-R base | **768** | Good for general sentences, weaker on specialized cross-lingual retrieval | None | Apache 2.0 | **Native 768**: Compatible, but lower MTEB retrieval performance than E5. |
| **Option D: `OpenAI text-embedding-3-small`** | Proprietary API | **1536** (can shorten to 768 via Matryoshka) | Strong general multilingual | None | Proprietary API call | Requires API egress; Matryoshka compression degrades Malayalam retrieval. |

---

## Verification of Candidate: `intfloat/multilingual-e5-base`

- **Model Card & Specifications**:
  - Base architecture: `xlm-roberta-base`
  - Max sequence length: 512 tokens
  - Hidden state dimension: **768**
  - Real embedding vector dimension: **768 float values**
  - Prefix contract:
    - Passages to index must be prefixed with: `"passage: <content>"`
    - Queries for search must be prefixed with: `"query: <question>"`
  - Asymmetry note: omitting prefixes leads to notable degradation in similarity scores.

---

## Decision

**Select `intfloat/multilingual-e5-base` as the primary embedding model.**

### Reasons:
1. **Exact Dimension Match (768)**: Directly satisfies the existing `Vector(768)` constraint in `knowledge_chunks.embedding`. No schema migration or index rebuild is required.
2. **Proven Multilingual Benchmark**: Evaluated on MTEB multilingual retrieval; strongly maps semantically equivalent English, Malayalam, and Hindi queries to nearby vector space.
3. **Standardized Per-Chunk Model Storage**: Each chunk persists `embedding_model = "intfloat/multilingual-e5-base"` in `knowledge_chunks.embedding_model`, allowing seamless zero-downtime model upgrades in the future if larger models (e.g. 1024d) are adopted later.
4. **Self-Hostable**: Can run locally or via lightweight ONNX Runtime with zero vendor cloud lock-in.

---

## Consequences

- Chunking pipeline must ensure passages are prefixed with `"passage: "` before vector calculation.
- Query pipeline must ensure user search input is prefixed with `"query: "` before vector calculation.
- Stored vectors are strictly normalized to unit length ($L_2 = 1.0$) so that cosine similarity equals dot product.
