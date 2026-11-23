# Phase 2 Engineering Notes: Knowledge Ingestion Pipeline

- **Branch**: `feat/ai-llm-rag`
- **Date**: 2026-11-22
- **Status**: Complete & Verified (136 tests passing, Ruff clean, Mypy clean)

---

## 1. What Was Built

### A) Database Schema & Alembic Migration
- **Migration**: `apps/api/migrations/versions/d5e6f7a8b9c0_expand_knowledge_schema.py`
  - Up & Down migrations for PostgreSQL + pgvector and SQLite.
  - Lifecycle state machine on `knowledge_documents`: `draft`, `processing`, `review`, `published`, `superseded`, `archived`.
  - Database-level constraints:
    - `ck_knowledge_documents_status`: Strict enum validation.
    - `ck_knowledge_documents_published_licence`: Refuses `published` status unless both `licence_note` and `source_url` are non-empty.
    - `ck_knowledge_chunks_embedding_dim`: Enforces 768 dimensions for `intfloat/multilingual-e5-base`.
    - `uq_knowledge_chunks_document_index`: Unique constraint on `(document_id, chunk_index)`.
  - Full-text search upgrade: Replaced `'english'` regconfig on `content_tsv` with `'simple'` regconfig to preserve Malayalam and Manglish token integrity without destructive English stemming.
  - SQL View: `published_knowledge_chunks` joining documents and chunks strictly where `status = 'published'`.

### B) Manifest & SSRF-Protected Fetcher
- **Manifest Engine** (`app/ai/rag/manifest.py` & `models.py`):
  - Strictly validates sources with Pydantic (`id`, `title`, `publisher`, `source_url`, `file_path`, `language`, `doc_type`, `licence_note`, dates, `reviewer`).
  - Automatically calculates allowed HTTPS domains.
- **SSRF-Protected URL Fetcher** (`app/ai/rag/fetcher.py`):
  - Enforces HTTPS scheme only.
  - Resolves DNS and blocks private (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), and multicast IP ranges.
  - Disallows domain-hopping redirects.
  - Enforces a 10MB payload size limit and allowed Content-Types (`text/html`, `application/pdf`, `text/markdown`, `text/plain`).

### C) Multi-Format Parsers & Text Cleaner
- **Parsers** (`app/ai/rag/parsers/`):
  - `MarkdownParser`: Tracks heading hierarchies (`#`, `##`, `###`), preserving heading paths (e.g. `I4C SOP > Section 503 BNSS > Route 1`).
  - `HTMLDocumentParser`: Drops `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`, and extracts clean structural text with headings.
  - `PDFDocumentParser`: Text stream extraction with section detection.
  - `PlainTextParser`: Paragraph-based chunking.
- **Unicode & Malayalam Cleaner** (`app/ai/rag/cleaner.py`):
  - Normalizes text to Unicode NFC form.
  - Fixes hyphenated line breaks (`pay-\nment` -> `payment`).
  - Strictly preserves Malayalam script (`\u0D00-\u0D7F`), chillu characters (`ൺ, ൻ, ർ, ൽ, ൾ, ൿ`), virama (`്`), Zero-Width Joiner (`\u200D`), and Zero-Width Non-Joiner (`\u200C`).
- **Language Detector** (`app/ai/rag/language.py`):
  - Uses Unicode script character counting for `ml` (Malayalam) and `hi` (Hindi).
  - Detects `manglish` via phonetic marker heuristics.
  - Reports `LANGUAGE_DISAGREEMENT` warnings when detected language differs from manifest.

### D) Structure-Aware Chunker & Security Scanner
- **Chunker** (`app/ai/rag/chunker.py`):
  - Target size: 400–600 tokens (max 800 tokens, 50–80 token overlap).
  - Calculates subword token inflation for Malayalam script.
  - Keeps table rows and list items contiguous without splitting.
  - Attaches `heading_path` to every chunk for clear citation in Phase 4.
- **Injection Scanner** (`app/ai/rag/security.py`):
  - Scans untrusted document content for instruction overrides (`"ignore previous instructions"`), chat template delimiters (`<|im_start|>`, `[INST]`), and fake role prefixes (`system:`, `developer:`).
  - Automatically holds documents with detected patterns in `review` with high-severity flags.

### E) Embedders, Lifecycle & Repository
- **Embedders** (`app/ai/rag/embedder/`):
  - `FakeEmbedder`: Deterministic, unit-normalized 768-dim vectors derived from SHA-256 for zero-network CI testing.
  - `LocalEmbedder`: Real CPU-based inference with `intfloat/multilingual-e5-base`, automatically applying `"passage: "` and `"query: "` prefixes per ADR-001.
- **Repository & State Machine** (`app/ai/rag/repository.py`):
  - `approve_document`: Enforces licence note, source URL, and runs a 3-query smoke retrieval check before allowing publication. Automatically marks prior active versions as `superseded`.
  - `reembed_document`: Performs atomic re-embedding of chunks in a single transaction.
  - `get_published_chunks`: Strictly excludes draft, processing, review, superseded, and archived chunks from retrieval.

### F) Ingestion CLI
- **CLI Commands** (`python -m app.ai.rag.ingest`):
  - `run`: Reads manifest, runs pipeline, puts documents into `review`.
  - `list`: Lists documents by lifecycle status.
  - `show <id>`: Displays document metadata, tokens, and chunk samples.
  - `approve <id>`: Validates licence, runs smoke check, publishes document, records reviewer.
  - `archive <id>`: Transitions to `archived`.
  - `reembed <id>`: Atomic re-embedding with new target model.

---

## 2. Exact Commands to Reproduce

```bash
# 1. Run all Phase 2 RAG tests (74 tests)
pytest tests/ai/test_rag_*.py

# 2. Run full backend test suite (136 tests)
pytest --ignore=tests/test_ml_models.py

# 3. Check code style and types
ruff check app tests
mypy app --ignore-missing-imports

# 4. Ingest sample manifest into development database
python -m app.ai.rag.ingest run --manifest data/knowledge/manifest.example.yaml

# 5. List and inspect ingested documents
python -m app.ai.rag.ingest list
python -m app.ai.rag.ingest show <doc_id>

# 6. Approve and publish a document
python -m app.ai.rag.ingest approve <doc_id> --reviewer "lead-compliance-officer"
```

---

## 3. Decisions & Trade-Offs

1. **`trim()` over `btrim()` in Check Constraints**:
   - `trim()` is ANSI standard and behaves identically in PostgreSQL and SQLite, preventing test suite errors when evaluating check constraints.
2. **`'simple'` regconfig for Sparse Search**:
   - Switched `content_tsv` from `'english'` to `'simple'` in migration `d5e6f7a8b9c0` to prevent destructive English stemming on Malayalam and Manglish terms.
3. **Graceful Dialect Adaptation in Unit Tests**:
   - Added compilation mappings (`compiles(TSVECTOR, 'sqlite')`, `compiles(Vector, 'sqlite')`, `compiles(Computed, 'sqlite')`) so the SQLAlchemy models can be instantiated seamlessly in fast local in-memory SQLite unit tests while generating true pgvector DDL on PostgreSQL.

---

## 4. Known Gaps / Transition to Phase 3
- The database now contains the schema and documents in `review`/`published`.
- Retrieval at query time (vector search, hybrid RRF, evaluation harness) belongs to **Phase 3**.
