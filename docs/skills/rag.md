# RAG skill
- Ingest (offline): manifest-approved source -> validate -> parse -> clean -> detect language -> chunk by headings and Q&A -> embed -> store in pgvector.
- Chunks: target 400-600 tokens, max 800, overlap 50-80. Count tokens with the embedder's tokenizer (Malayalam inflates counts).
- Embedder: multilingual-e5-base, 768 dims, must match the vector(768) column. Prefix "passage: " for chunks, "query: " for questions. Store embedding_model per chunk; re-embed on model change.
- Lifecycle: draft -> processing -> review -> published -> superseded -> archived. Only `published` is retrievable. Unchanged content hash = no-op.
- Retrieval: vector + keyword (pg_trgm or simple FTS; the english config is weak for Malayalam/Manglish) -> RRF (k=60) -> optional reranker. 20+20 candidates, return 5-8. Filters: published, optional language.
- Answer: evidence aliases E1, E2 mapped server-side to chunk ids, inside delimited untrusted-data blocks. Abstain BEFORE the LLM if evidence is weak. Validate citations, numbers, contacts, policy. Fallback: extractive snippets.
- Eval: Recall@K, MRR, nDCG with 95% CI; compare vector vs keyword vs hybrid vs +reranker. Use the real embedder; fake-embedder numbers mean nothing.

## Dataset generation and evaluation workflow
1. **Dataset Generation CLI**:
   - `python -m app.ai.evals.datagen --target 100 --provider fake --output evals/data/rag_dataset_draft.jsonl --export-csv evals/data/rag_dataset_draft.csv`
   - Use `--provider configured` to generate paraphrased Q&A pairs via LLM (Groq free tier with throttle, caching, and 429 backoff).
   - Generated items output with status `draft`. Malayalam and Manglish cases are flagged `needs_native_review=True`.
2. **Human Review Loop**:
   - Review drafts in `evals/data/rag_dataset_draft.csv`. Mark `review_action` as `approve`, `edit`, or `reject`.
   - Cases with `approve` or `edit` become status `reviewed`.
   - Deterministic dev/test splitting via `app.ai.evals.review.split_reviewed_cases(cases, seed=42)` (tune only on `dev`).
3. **Experiment Runner CLI**:
   - `python -m app.ai.evals.experiment --dataset evals/data/rag_dataset_draft.jsonl --split dev --mode hybrid --sweep-thresholds`
   - Modes: `vector-only`, `keyword-only`, `hybrid`, `all`. Options: `--top-k 5`, `--rrf-k 60`, `--reranker`, `--provider configured|fake`.
   - Outputs timestamped JSON report to `evals/reports/` with Wilson 95% CIs (proportions) and bootstrap 95% CIs (continuous metrics), per-language breakdowns, and worst-case reason codes (`retrieval_miss`, `wrong_abstention`, `bad_citation`, `language_fallback`, `validation_failure`).
4. **Analysis & Visualization**:
   - Jupyter Notebook: `evals/notebooks/rag_experiments.ipynb` loads reports from `evals/reports/` and renders config comparisons, threshold curves, and error breakdowns.
   - Static HTML fallback: `python -m app.ai.evals.report_html --reports-dir evals/reports --output evals/reports/index.html`.
