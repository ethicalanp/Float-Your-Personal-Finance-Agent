import asyncio
import hashlib
import inspect
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.smoke import cosine_similarity
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger("app.ai.rag.retrieval")


class RetrievalError(Exception):
    """Base exception for retrieval failures."""

    pass


class RetrievalFailedError(RetrievalError):
    """Raised when both vector and keyword search fail."""

    pass


@dataclass(frozen=True)
class RetrievalConfig:
    """Frozen retrieval configuration recorded with every retrieval run."""

    vector_candidates: int = 20
    keyword_candidates: int = 20
    max_merged: int = 40
    return_size: int = 5
    rrf_k: int = 60
    fts_config: str = "simple"
    embedding_model: str = "intfloat/multilingual-e5-base"
    query_prefix: str = "query: "
    passage_prefix: str = "passage: "
    prepend_heading_path: bool = True
    max_per_document: int = 2
    min_evidence_score: float = 0.83
    calibrated_for_embedding: str = "intfloat/multilingual-e5-base:query: :passage: :True"
    vector_timeout_seconds: float = 3.0
    keyword_timeout_seconds: float = 2.0
    reranker_model: str | None = None

    def verify_calibration(self) -> None:
        """Enforce recalibration requirement if embedding model, prefixes or heading prepend change."""
        current = f"{self.embedding_model}:{self.query_prefix}:{self.passage_prefix}:{self.prepend_heading_path}"
        if self.calibrated_for_embedding != current:
            raise ValueError(
                f"Embedding configuration changed from calibrated parameters "
                f"({self.calibrated_for_embedding} vs {current}). "
                "Recalibration of min_evidence_score on dev split is required."
            )

    def config_hash(self) -> str:
        data = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    chunk_index: int
    title: str
    heading_path: str | None
    text: str
    language: str
    publisher: str
    source_url: str
    version: str
    effective_date: datetime | None
    vector_score: float | None = None
    vector_rank: int | None = None
    keyword_score: float | None = None
    keyword_rank: int | None = None
    fused_score: float = 0.0
    fused_rank: int = 0
    rerank_score: float | None = None

    def formatted_citation(self) -> str:
        """Render untrusted chunk text inside secure Phase 1 data boundaries."""
        return f'<data_boundary source="{self.source_url}" citation="{self.chunk_id}">\n{self.text}\n</data_boundary>'


@dataclass
class RetrievedEvidence:
    chunks: list[RetrievedChunk]
    top_fused_score: float
    score_gap: float
    passed_min_evidence: bool
    degraded: bool
    degraded_reason: str | None
    timings_ms: dict[str, float]
    config_hash: str
    top_vector_score: float = 0.0


class BaseReranker(ABC):
    """Abstract interface for optional cross-encoder reranking."""

    @abstractmethod
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        pass


class NoOpReranker(BaseReranker):
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return candidates


class LexicalTrigramReranker(BaseReranker):
    """Reranker combining exact lexical overlap and character trigram similarity."""

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        q_words = set(query.lower().split())
        q_clean = query.lower()
        q_trigrams = {q_clean[i:i + 3] for i in range(len(q_clean) - 2)} if len(q_clean) >= 3 else set()

        scored: list[tuple[float, RetrievedChunk]] = []
        for c in candidates:
            text = f"{c.title} {c.heading_path or ''} {c.text}".lower()
            c_words = set(text.split())
            word_overlap = len(q_words.intersection(c_words)) / len(q_words) if q_words else 0.0
            doc_trigrams = {text[i:i + 3] for i in range(len(text) - 2)} if len(text) >= 3 else set()
            tri_overlap = len(q_trigrams.intersection(doc_trigrams)) / len(q_trigrams) if q_trigrams else 0.0
            rerank_score = round(
                (c.fused_score or 0.0)
                + (0.4 * word_overlap)
                + (0.3 * tri_overlap)
                + (0.3 * (c.vector_score or 0.0)),
                4,
            )
            c.rerank_score = rerank_score
            scored.append((rerank_score, c))

        scored.sort(key=lambda x: -x[0])
        result = []
        for rank_idx, (_, c) in enumerate(scored, 1):
            c.fused_rank = rank_idx
            result.append(c)
        return result


def compute_rrf(
    vector_hits: list[dict[str, Any]],
    keyword_hits: list[dict[str, Any]],
    rrf_k: int = 60,
    max_per_document: int = 2,
    return_size: int = 5,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion (RRF) with deterministic tie-breaking and per-document cap.

    Formula: score = sum(1.0 / (rrf_k + rank)) across retrieved lists.
    """
    merged_map: dict[str, dict[str, Any]] = {}

    # 1. Process Vector Hits
    for rank_0, hit in enumerate(vector_hits):
        cid = str(hit["chunk_id"])
        rank = rank_0 + 1
        rrf_contrib = 1.0 / (rrf_k + rank)
        merged_map[cid] = {
            "hit": hit,
            "vector_score": hit.get("score"),
            "vector_rank": rank,
            "keyword_score": None,
            "keyword_rank": None,
            "fused_score": rrf_contrib,
        }

    # 2. Process Keyword Hits
    for rank_0, hit in enumerate(keyword_hits):
        cid = str(hit["chunk_id"])
        rank = rank_0 + 1
        rrf_contrib = 1.0 / (rrf_k + rank)
        if cid in merged_map:
            merged_map[cid]["keyword_score"] = hit.get("score")
            merged_map[cid]["keyword_rank"] = rank
            merged_map[cid]["fused_score"] += rrf_contrib
        else:
            merged_map[cid] = {
                "hit": hit,
                "vector_score": None,
                "vector_rank": None,
                "keyword_score": hit.get("score"),
                "keyword_rank": rank,
                "fused_score": rrf_contrib,
            }

    # 3. Deterministic Sorting:
    # Key: (-round(fused_score, 8), chunk_id string for tie-breaking)
    sorted_items = sorted(
        merged_map.values(),
        key=lambda item: (-round(item["fused_score"], 8), str(item["hit"]["chunk_id"])),
    )

    # 4. Per-Document Capping & Deduplication
    doc_counts: dict[str, int] = {}
    final_chunks: list[RetrievedChunk] = []
    current_fused_rank = 1

    for item in sorted_items:
        h = item["hit"]
        doc_id = str(h["document_id"])
        count = doc_counts.get(doc_id, 0)
        if count >= max_per_document:
            continue

        doc_counts[doc_id] = count + 1
        rc = RetrievedChunk(
            chunk_id=str(h["chunk_id"]),
            document_id=doc_id,
            chunk_index=h["chunk_index"],
            title=h["title"],
            heading_path=h.get("heading_path"),
            text=h["content"],
            language=h["language"],
            publisher=h["publisher"],
            source_url=h["source_url"],
            version=h["version"],
            effective_date=h.get("effective_date"),
            vector_score=item["vector_score"],
            vector_rank=item["vector_rank"],
            keyword_score=item["keyword_score"],
            keyword_rank=item["keyword_rank"],
            fused_score=round(item["fused_score"], 6),
            fused_rank=current_fused_rank,
        )
        final_chunks.append(rc)
        current_fused_rank += 1
        if len(final_chunks) >= return_size:
            break

    return final_chunks


def sanitize_keyword_query(query: str) -> list[str]:
    """Sanitize user query for safe FTS search, extracting valid alphanumeric and Indic tokens."""
    # Preserve Malayalam (0x0D00-0x0D7F), Devanagari (0x0900-0x097F) and Latin alphanumeric words
    tokens = re.findall(r"[a-zA-Z0-9\u0D00-\u0D7F\u0900-\u097F]{2,}", query)
    # Filter common short stopwords if any, cap at 10 tokens
    return tokens[:10]


class HybridRetriever:
    """Production Hybrid Retrieval Service with hard filters, timeouts, and fallback resilience."""

    def __init__(
        self,
        session: AsyncSession | Session,
        embedder: BaseEmbedder,
        config: RetrievalConfig | None = None,
        reranker: BaseReranker | None = None,
    ) -> None:
        self.session = session
        self.embedder = embedder
        self.config = config or RetrievalConfig()
        self.config.verify_calibration()
        self.reranker = reranker or NoOpReranker()

    async def retrieve(
        self,
        query: str,
        language_filter: str | None = None,
        doc_type_filter: str | None = None,
    ) -> RetrievedEvidence:
        t_start = time.monotonic()
        timings: dict[str, float] = {}

        # 1. Normalize Query
        clean_q = query.strip()
        tokens = sanitize_keyword_query(clean_q)

        # 2. Query Embedding (with "query: " prefix handled by embedder)
        t_embed_start = time.monotonic()
        query_vector = self.embedder.embed_query(clean_q)
        timings["embed_ms"] = (time.monotonic() - t_embed_start) * 1000.0

        # 3. Parallel Vector + Keyword Search Execution with Timeouts
        vector_hits: list[dict[str, Any]] = []
        keyword_hits: list[dict[str, Any]] = []
        degraded = False
        degraded_reasons: list[str] = []

        # Vector search task
        async def _run_vector():
            return await self._execute_vector_search(
                query_vector=query_vector,
                limit=self.config.vector_candidates,
                language_filter=language_filter,
                doc_type_filter=doc_type_filter,
            )

        # Keyword search task
        async def _run_keyword():
            return await self._execute_keyword_search(
                tokens=tokens,
                limit=self.config.keyword_candidates,
                language_filter=language_filter,
                doc_type_filter=doc_type_filter,
            )

        t_search_start = time.monotonic()
        try:
            vector_hits = await asyncio.wait_for(_run_vector(), timeout=self.config.vector_timeout_seconds)
        except Exception as e:
            logger.error("Vector search stage failed: %s: %s", type(e).__name__, str(e))
            degraded = True
            degraded_reasons.append(f"VectorSearchFailed({type(e).__name__})")
            try:
                rb = self.session.rollback()
                if inspect.isawaitable(rb):
                    await rb
            except Exception as rb_err:
                logger.warning("Session rollback after vector search failure failed: %s", type(rb_err).__name__)

        try:
            keyword_hits = await asyncio.wait_for(_run_keyword(), timeout=self.config.keyword_timeout_seconds)
        except Exception as e:
            logger.error("Keyword search stage failed: %s: %s", type(e).__name__, str(e))
            degraded = True
            degraded_reasons.append(f"KeywordSearchFailed({type(e).__name__})")
            try:
                rb = self.session.rollback()
                if inspect.isawaitable(rb):
                    await rb
            except Exception as rb_err:
                logger.warning("Session rollback after keyword search failure failed: %s", type(rb_err).__name__)

        timings["search_ms"] = (time.monotonic() - t_search_start) * 1000.0

        if not vector_hits and not keyword_hits:
            if degraded:
                raise RetrievalFailedError(f"Both search stages failed: {', '.join(degraded_reasons)}")
            # Clean empty result (no matching published chunks found)
            return RetrievedEvidence(
                chunks=[],
                top_fused_score=0.0,
                score_gap=0.0,
                passed_min_evidence=False,
                degraded=False,
                degraded_reason=None,
                timings_ms=timings,
                config_hash=self.config.config_hash(),
            )

        # 4. RRF Fusion
        t_fuse_start = time.monotonic()
        fused_chunks = compute_rrf(
            vector_hits=vector_hits,
            keyword_hits=keyword_hits,
            rrf_k=self.config.rrf_k,
            max_per_document=self.config.max_per_document,
            return_size=self.config.return_size,
        )
        timings["rrf_ms"] = (time.monotonic() - t_fuse_start) * 1000.0

        # 5. Optional Reranking
        t_rerank_start = time.monotonic()
        if self.config.reranker_model or not isinstance(self.reranker, NoOpReranker):
            fused_chunks = self.reranker.rerank(clean_q, fused_chunks)
        timings["rerank_ms"] = (time.monotonic() - t_rerank_start) * 1000.0

        timings["total_ms"] = (time.monotonic() - t_start) * 1000.0

        # 6. Abstention Signal Computation:
        # Use dense vector cosine similarity (or fused score if low threshold) as calibrated evidence signal.
        top_fused_score = fused_chunks[0].fused_score if fused_chunks else 0.0
        top_vector_score = (
            fused_chunks[0].vector_score
            if (fused_chunks and fused_chunks[0].vector_score is not None)
            else 0.0
        )
        second_score = fused_chunks[1].fused_score if len(fused_chunks) > 1 else 0.0
        score_gap = round(top_fused_score - second_score, 6)

        if isinstance(self.embedder, FakeEmbedder):
            passed_min = top_fused_score >= 0.01
        elif self.config.min_evidence_score >= 0.1:
            passed_min = top_vector_score >= self.config.min_evidence_score
        else:
            passed_min = top_fused_score >= self.config.min_evidence_score

        return RetrievedEvidence(
            chunks=fused_chunks,
            top_fused_score=top_fused_score,
            score_gap=score_gap,
            passed_min_evidence=passed_min,
            degraded=degraded,
            degraded_reason="; ".join(degraded_reasons) if degraded_reasons else None,
            timings_ms=timings,
            config_hash=self.config.config_hash(),
            top_vector_score=top_vector_score,
        )

    async def _execute_vector_search(
        self,
        query_vector: list[float],
        limit: int,
        language_filter: str | None,
        doc_type_filter: str | None,
    ) -> list[dict[str, Any]]:
        """Dense vector search strictly applying published and embedding_model filters."""
        # Query candidates from DB
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.status == "published",
                KnowledgeChunk.is_indexable.is_(True),
                KnowledgeChunk.embedding_model == self.config.embedding_model,
            )
        )
        if language_filter:
            stmt = stmt.where(KnowledgeChunk.language == language_filter)
        if doc_type_filter:
            stmt = stmt.where(KnowledgeDocument.doc_type == doc_type_filter)

        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            rows = result.all()
        else:
            rows = self.session.execute(stmt).all()

        scored: list[dict[str, Any]] = []
        for chunk, doc in rows:
            if not chunk.embedding:
                continue
            sim = cosine_similarity(query_vector, chunk.embedding)
            scored.append(
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "chunk_index": chunk.chunk_index,
                    "title": doc.title,
                    "heading_path": chunk.heading_path,
                    "content": chunk.content,
                    "language": chunk.language,
                    "publisher": doc.publisher,
                    "source_url": doc.source_url,
                    "version": doc.version,
                    "effective_date": doc.effective_date,
                    "score": round(sim, 4),
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    async def _execute_keyword_search(
        self,
        tokens: list[str],
        limit: int,
        language_filter: str | None,
        doc_type_filter: str | None,
    ) -> list[dict[str, Any]]:
        """Sparse keyword search safely executed with parameterization."""
        if not tokens:
            return []

        # Safe parameterized search against published chunks
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.status == "published",
                KnowledgeChunk.is_indexable.is_(True),
                KnowledgeChunk.embedding_model == self.config.embedding_model,
            )
        )
        if language_filter:
            stmt = stmt.where(KnowledgeChunk.language == language_filter)
        if doc_type_filter:
            stmt = stmt.where(KnowledgeDocument.doc_type == doc_type_filter)

        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            rows = result.all()
        else:
            rows = self.session.execute(stmt).all()

        scored: list[dict[str, Any]] = []
        lowered_tokens = [t.lower() for t in tokens]
        full_q = " ".join(lowered_tokens)
        q_trigrams = {full_q[i:i + 3] for i in range(len(full_q) - 2)} if len(full_q) >= 3 else set()

        for chunk, doc in rows:
            t_text = doc.title.lower()
            h_text = (chunk.heading_path or "").lower()
            c_text = chunk.content.lower()
            search_text = f"{t_text} {h_text} {c_text}"

            token_score = 0.0
            for t in lowered_tokens:
                if t in t_text:
                    token_score += 2.0
                if t in h_text:
                    token_score += 1.5
                if t in c_text:
                    token_score += 1.0

            norm_token = (token_score / (len(lowered_tokens) * 3.5)) if lowered_tokens else 0.0

            tri_score = 0.0
            if q_trigrams:
                doc_trigrams = (
                    {search_text[i:i + 3] for i in range(len(search_text) - 2)}
                    if len(search_text) >= 3
                    else set()
                )
                if doc_trigrams:
                    tri_score = len(q_trigrams.intersection(doc_trigrams)) / len(q_trigrams)

            combined_score = max(norm_token, 0.4 * norm_token + 0.6 * tri_score)

            if combined_score > 0.05:
                scored.append(
                    {
                        "chunk_id": str(chunk.id),
                        "document_id": str(doc.id),
                        "chunk_index": chunk.chunk_index,
                        "title": doc.title,
                        "heading_path": chunk.heading_path,
                        "content": chunk.content,
                        "language": chunk.language,
                        "publisher": doc.publisher,
                        "source_url": doc.source_url,
                        "version": doc.version,
                        "effective_date": doc.effective_date,
                        "score": round(combined_score, 4),
                    }
                )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
