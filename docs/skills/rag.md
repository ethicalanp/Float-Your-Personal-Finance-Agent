# RAG skill
- Ingest (offline): manifest-approved source -> validate -> parse -> clean -> detect language -> chunk by headings and Q&A -> embed -> store in pgvector.
- Chunks: target 400-600 tokens, max 800, overlap 50-80. Count tokens with the embedder's tokenizer (Malayalam inflates counts).
- Embedder: multilingual-e5-base, 768 dims, must match the vector(768) column. Prefix "passage: " for chunks, "query: " for questions. Store embedding_model per chunk; re-embed on model change.
- Lifecycle: draft -> processing -> review -> published -> superseded -> archived. Only `published` is retrievable. Unchanged content hash = no-op.
- Retrieval: vector + keyword (pg_trgm or simple FTS; the english config is weak for Malayalam/Manglish) -> RRF (k=60) -> optional reranker. 20+20 candidates, return 5-8. Filters: published, optional language.
- Answer: evidence aliases E1, E2 mapped server-side to chunk ids, inside delimited untrusted-data blocks. Abstain BEFORE the LLM if evidence is weak. Validate citations, numbers, contacts, policy. Fallback: extractive snippets.
- Eval: Recall@K, MRR, nDCG with 95% CI; compare vector vs keyword vs hybrid vs +reranker. Use the real embedder; fake-embedder numbers mean nothing.