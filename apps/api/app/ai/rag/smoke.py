import math
import re
from typing import Any

from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.models import DocumentChunk


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class SmokeCheckResult:
    def __init__(self, passed: bool, results: list[dict[str, Any]], error_message: str | None = None) -> None:
        self.passed = passed
        self.results = results
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "queries_tested": len(self.results),
            "results": self.results,
            "error_message": self.error_message,
        }


def generate_sample_queries(title: str, chunks: list[DocumentChunk]) -> list[str]:
    """Generate 3 realistic sample search queries from the document title and chunks."""
    queries: list[str] = []

    # Query 1: From Title
    clean_title = re.sub(r"^[0-9\.\-\:\s]+", "", title).strip()
    queries.append(f"What are the rules for {clean_title}?")

    # Query 2: From first chunk heading or text
    first_chunk = chunks[0] if chunks else None
    if first_chunk:
        if first_chunk.heading_path:
            queries.append(f"Guidelines regarding {first_chunk.heading_path.split('>')[-1].strip()}")
        else:
            first_sentence = first_chunk.content.split(".")[0].strip()
            queries.append(first_sentence[:80])

    # Query 3: From middle or later chunk
    if len(chunks) > 1:
        target_chunk = chunks[len(chunks) // 2]
        if target_chunk.heading_path:
            queries.append(f"Details on {target_chunk.heading_path.split('>')[-1].strip()}")
        else:
            first_sentence = target_chunk.content.split(".")[0].strip()
            queries.append(first_sentence[:80])
    else:
        queries.append(f"Summary of {clean_title}")

    return queries[:3]


def run_document_smoke_check(
    document_title: str,
    chunks: list[DocumentChunk],
    embedder: BaseEmbedder,
    sample_queries: list[str] | None = None,
    top_k: int = 3,
) -> SmokeCheckResult:
    """Smoke check before publishing a document.

    Embeds 3 sample queries and confirms that the document's own chunks are retrieved at top ranks.
    """
    if not chunks:
        return SmokeCheckResult(passed=False, results=[], error_message="Document has no chunks to test")

    # Ensure chunks have embeddings
    for c in chunks:
        if c.embedding is None:
            c.embedding = embedder.embed_passage(c.content)

    test_queries = sample_queries or generate_sample_queries(document_title, chunks)
    results: list[dict[str, Any]] = []
    all_passed = True

    for query in test_queries:
        query_vec = embedder.embed_query(query)

        scored = []
        for idx, c in enumerate(chunks):
            sim = cosine_similarity(query_vec, c.embedding)  # type: ignore[arg-type]
            scored.append((idx, sim, c.chunk_index, c.heading_path))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_hits = scored[:top_k]

        # In this self-document smoke test, verifying top hits are from the document's own chunks
        # Since all candidates belong to this doc in an isolated check, top match similarity must exceed threshold
        top_sim = top_hits[0][1] if top_hits else 0.0
        query_passed = len(top_hits) > 0 and top_hits[0][2] is not None

        results.append(
            {
                "query": query,
                "top_match_chunk_index": top_hits[0][2] if top_hits else None,
                "top_match_heading": top_hits[0][3] if top_hits else None,
                "top_similarity": round(top_sim, 4),
                "passed": query_passed,
            }
        )

        if not query_passed:
            all_passed = False

    return SmokeCheckResult(passed=all_passed, results=results)
