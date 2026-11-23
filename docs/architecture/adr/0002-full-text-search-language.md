# ADR-002: Full-Text Search Configuration for Multilingual and Transliterated Text

- **Status**: Proposed (To be decided empirically via Phase 2 evaluation)
- **Date**: 2026-11-22
- **Area**: RAG / Sparse Keyword Search

---

## Context

In `app/models/knowledge.py`, the sparse search column `content_tsv` is currently defined as:
```python
content_tsv: Mapped[str] = mapped_column(
    TSVECTOR,
    Computed("to_tsvector('english'::regconfig, content)", persisted=True),
)
```
And indexed with:
```python
Index("idx_knowledge_chunks_content_tsv", "content_tsv", postgresql_using="gin")
```

### The Problem
- The `'english'` text search configuration applies English stemming (Porter stemmer) and English stopword filtering.
- For **Malayalam script** (`[\u0D00-\u0D7F]`), PostgreSQL's English dictionary fails to stem words, treats complex compound agglutinations as monolithic unknown tokens, or drops characters.
- For **Manglish** (phonetically transliterated Malayalam in Latin characters, e.g., *"panam"*, *"adakkillel"*, *"linkil"*), English stemming chops off endings inappropriately (e.g. treating *"panam"* as an English word or corrupting prefixes).
- A purely English `to_tsvector` produces near-zero sparse recall for regional vernacular documents and user queries.

---

## Options Proposed for Evaluation

### Option 1: `'simple'` Regconfig
- **Mechanism**: `to_tsvector('simple'::regconfig, content)`.
- **How it works**: Lowercases tokens and splits on whitespace/punctuation without applying language-specific stemming or stopword lists.
- **Pros**: Language-neutral; indexes exact tokens in English, Malayalam script, and Manglish identically; avoids erroneous Porter stem truncation.
- **Cons**: Does not handle inflections (e.g., Malayalam case endings like -il, -nte, -ukal, or English plurals).

### Option 2: `pg_trgm` Trigram Similarity Index
- **Mechanism**: Enable `CREATE EXTENSION IF NOT EXISTS pg_trgm;` and create a GIN trigram index on raw `content`:
  ```sql
  CREATE INDEX idx_knowledge_chunks_content_trgm ON knowledge_chunks USING gin (content gin_trgm_ops);
  ```
- **How it works**: Breaks words into 3-character sequences. Evaluates fuzzy string overlap via `similarity(content, query)` or `%` operator.
- **Pros**: Exceptional for:
  - Phonetic spelling variants in Manglish (e.g., *"cheyyuka"* vs *"cheyyu"* vs *"cheyyanam"*).
  - Morphologically rich Malayalam agglutinative roots.
  - Typos in bank names, merchant names, or scheme names.
- **Cons**: Trigram index size is larger than tsvector; exact queries can be slower on very large corpora (negligible under 100k chunks).

### Option 3: Per-Chunk Language-Aware Configuration
- **Mechanism**: Add a `language` column (`en`, `ml`, `hi`, `und`) to `knowledge_chunks`.
- Compute `content_tsv` dynamically based on chunk language:
  ```sql
  CASE 
    WHEN language = 'en' THEN to_tsvector('english'::regconfig, content)
    ELSE to_tsvector('simple'::regconfig, content)
  END
  ```
- **Pros**: English documents retain English stemming; non-English/multilingual chunks use `'simple'`.
- **Cons**: Requires migration and metadata tagging at ingestion; does not solve Manglish phonetic spelling variance.

### Option 4: Hybrid Dual Sparse Index (`'simple'` TSVECTOR + `pg_trgm`)
- **Mechanism**: Use `'simple'` tsvector for fast keyword lookup combined with `pg_trgm` similarity for fuzzy transliterated matching, fused with dense vector retrieval via Reciprocal Rank Fusion (RRF).

---

## Evaluation Plan & Decision Criteria (Phase 2)

Rather than guessing which sparse approach is best, the final choice will be decided based on empirical benchmark results in **Phase 2 Retrieval Evaluation**:

1. **Test Dataset**:
   - 30 curated bilingual test queries:
     - 10 in English (e.g., "compensation for failed ATM withdrawal")
     - 10 in Malayalam script (e.g., "വൈദ്യുതി ബിൽ തട്ടിപ്പ് പരാതി")
     - 10 in Manglish (e.g., "electricity bill scam vannal enthu cheyyanam")
2. **Metrics**:
   - Sparse Recall@5 (fraction of queries where ground-truth document is retrieved).
   - Mean Reciprocal Rank (MRR@5).
   - Index storage overhead and query execution latency in milliseconds.

---

## Status

**Open for Phase 2 Empirical Benchmark**. Until benchmark results are recorded, the pipeline will prototype with Option 4 (`'simple'` + `pg_trgm` candidate).
