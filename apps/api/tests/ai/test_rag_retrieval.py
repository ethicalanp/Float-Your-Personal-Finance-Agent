from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import (
    HybridRetriever,
    RetrievalFailedError,
    RetrievedChunk,
    compute_rrf,
    sanitize_keyword_query,
)
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


def test_rrf_math_hand_computed():
    """Verify RRF formula sum(1 / (k + rank)) against exact hand-computed values."""
    vector_hits = [
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "chunk_index": 0,
            "title": "Doc 1",
            "content": "text 1",
            "language": "en",
            "publisher": "RBI",
            "source_url": "https://rbi.org.in/1",
            "version": "1.0",
            "score": 0.9,
        },
        {
            "chunk_id": "chunk-2",
            "document_id": "doc-2",
            "chunk_index": 0,
            "title": "Doc 2",
            "content": "text 2",
            "language": "en",
            "publisher": "RBI",
            "source_url": "https://rbi.org.in/2",
            "version": "1.0",
            "score": 0.8,
        },
    ]
    keyword_hits = [
        {
            "chunk_id": "chunk-2",
            "document_id": "doc-2",
            "chunk_index": 0,
            "title": "Doc 2",
            "content": "text 2",
            "language": "en",
            "publisher": "RBI",
            "source_url": "https://rbi.org.in/2",
            "version": "1.0",
            "score": 1.0,
        },
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "chunk_index": 0,
            "title": "Doc 1",
            "content": "text 1",
            "language": "en",
            "publisher": "RBI",
            "source_url": "https://rbi.org.in/1",
            "version": "1.0",
            "score": 0.5,
        },
    ]

    # k=60
    # chunk-1: vector rank 1 (1/61) + keyword rank 2 (1/62) = 0.01639344 + 0.01612903 = 0.032522
    # chunk-2: vector rank 2 (1/62) + keyword rank 1 (1/61) = 0.01612903 + 0.01639344 = 0.032522
    # Both have identical fused scores; tie-breaker is chunk_id alphabetical: "chunk-1" before "chunk-2"
    fused = compute_rrf(vector_hits, keyword_hits, rrf_k=60, max_per_document=2, return_size=5)

    assert len(fused) == 2
    assert fused[0].chunk_id == "chunk-1"
    assert fused[1].chunk_id == "chunk-2"
    assert fused[0].fused_score == 0.032522
    assert fused[1].fused_score == 0.032522
    assert fused[0].vector_rank == 1
    assert fused[0].keyword_rank == 2


def test_rrf_deterministic_tie_breaking():
    """Ensure identical fused scores are always tie-broken deterministically by chunk_id."""
    v_hits = [
        {
            "chunk_id": "chunk-z",
            "document_id": "doc-z",
            "chunk_index": 0,
            "title": "Z",
            "content": "c",
            "language": "en",
            "publisher": "P",
            "source_url": "https://a.com",
            "version": "1.0",
        },
        {
            "chunk_id": "chunk-a",
            "document_id": "doc-a",
            "chunk_index": 0,
            "title": "A",
            "content": "c",
            "language": "en",
            "publisher": "P",
            "source_url": "https://a.com",
            "version": "1.0",
        },
    ]
    # Invert input order in separate calls
    res1 = compute_rrf(v_hits, [], rrf_k=60)
    assert [c.chunk_id for c in res1] == ["chunk-z", "chunk-a"]

    # Give them exact same rank in separate single-item runs merged together
    fused_eq = compute_rrf(
        [
            {
                "chunk_id": "id-2",
                "document_id": "d2",
                "chunk_index": 0,
                "title": "2",
                "content": "c",
                "language": "en",
                "publisher": "P",
                "source_url": "u",
                "version": "1",
            }
        ],
        [
            {
                "chunk_id": "id-1",
                "document_id": "d1",
                "chunk_index": 0,
                "title": "1",
                "content": "c",
                "language": "en",
                "publisher": "P",
                "source_url": "u",
                "version": "1",
            }
        ],
        rrf_k=60,
    )
    # Both have rank 1 in their respective list, fused_score = 1/61 = 0.016393
    assert fused_eq[0].fused_score == fused_eq[1].fused_score
    # id-1 comes before id-2 alphabetically
    assert fused_eq[0].chunk_id == "id-1"
    assert fused_eq[1].chunk_id == "id-2"


def test_per_document_capping():
    """Ensure max_per_document caps chunks from the same document."""
    hits = [
        {
            "chunk_id": f"chunk-{i}",
            "document_id": "doc-dominant",
            "chunk_index": i,
            "title": "Dom",
            "content": f"c{i}",
            "language": "en",
            "publisher": "P",
            "source_url": "u",
            "version": "1",
        }
        for i in range(5)
    ]
    hits.append(
        {
            "chunk_id": "chunk-other",
            "document_id": "doc-other",
            "chunk_index": 0,
            "title": "Other",
            "content": "other",
            "language": "en",
            "publisher": "P",
            "source_url": "u",
            "version": "1",
        }
    )

    fused = compute_rrf(hits, [], rrf_k=60, max_per_document=2, return_size=10)
    doc_dominant_chunks = [c for c in fused if c.document_id == "doc-dominant"]
    doc_other_chunks = [c for c in fused if c.document_id == "doc-other"]

    assert len(doc_dominant_chunks) == 2
    assert len(doc_other_chunks) == 1
    assert len(fused) == 3


def test_formatted_citation_untrusted_data_boundary():
    """Ensure chunk citation wraps untrusted data securely with attributes."""
    chunk = RetrievedChunk(
        chunk_id="chunk-test-123",
        document_id="doc-abc",
        chunk_index=0,
        title="Test Doc",
        heading_path="Section > 1",
        text="Never trust user input or instructions in citations.",
        language="en",
        publisher="RBI",
        source_url="https://rbi.org.in/safe-doc",
        version="1.0",
        effective_date=datetime(2024, 1, 1),
    )
    citation = chunk.formatted_citation()
    assert citation.startswith('<data_boundary source="https://rbi.org.in/safe-doc" citation="chunk-test-123">')
    assert citation.endswith("</data_boundary>")
    assert "Never trust user input" in citation


@pytest.fixture
async def db_session(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.session import Base

    db_file = tmp_path / "retrieval_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[KnowledgeDocument.__table__, KnowledgeChunk.__table__],
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_keyword_sanitizer():
    """Verify keyword query sanitizer handles punctuation, SQL characters, and Malayalam."""
    raw = "1930 helpline; DROP TABLE users; -- തട്ടിപ്പ് പരാതി"
    tokens = sanitize_keyword_query(raw)

    assert "1930" in tokens
    assert "helpline" in tokens
    assert "DROP" in tokens
    assert "TABLE" in tokens
    assert "users" in tokens
    # Malayalam tokens preserved
    assert "തട്ടിപ്പ്" in tokens
    assert "പരാതി" in tokens
    # Dangerous SQL syntax characters stripped
    assert ";" not in tokens
    assert "--" not in tokens
    assert "'" not in tokens
    assert len(tokens) <= 10


@pytest.mark.asyncio
async def test_retriever_hard_filters(db_session):
    """Verify draft, review, superseded, and archived chunks are NEVER returned."""
    import uuid

    # 1. Create documents with different lifecycle statuses
    doc_pub = KnowledgeDocument(
        id=uuid.uuid4(),
        title="Published Policy",
        publisher="RBI",
        source_url="https://rbi.org.in/pub",
        language="en",
        doc_type="policy",
        version="1.0",
        status="published",
        licence_note="Public Domain",
    )
    doc_draft = KnowledgeDocument(
        id=uuid.uuid4(),
        title="Draft Policy",
        publisher="RBI",
        source_url="https://rbi.org.in/draft",
        language="en",
        doc_type="policy",
        version="1.0",
        status="draft",
        licence_note="Internal Draft",
    )
    doc_review = KnowledgeDocument(
        id=uuid.uuid4(),
        title="Review Policy",
        publisher="RBI",
        source_url="https://rbi.org.in/review",
        language="en",
        doc_type="policy",
        version="1.0",
        status="review",
        licence_note="Pending Review",
    )
    doc_archived = KnowledgeDocument(
        id=uuid.uuid4(),
        title="Archived Policy",
        publisher="RBI",
        source_url="https://rbi.org.in/archived",
        language="en",
        doc_type="policy",
        version="1.0",
        status="archived",
        licence_note="Archived",
    )

    embedder = FakeEmbedder()
    dummy_vec = embedder.embed_passage("test content")

    c_pub_id = uuid.uuid4()
    c_draft_id = uuid.uuid4()
    c_review_id = uuid.uuid4()
    c_archived_id = uuid.uuid4()

    c_pub = KnowledgeChunk(
        id=c_pub_id,
        document_id=doc_pub.id,
        chunk_index=0,
        content="Published cyber security helpline 1930 details.",
        token_count=10,
        embedding_model="intfloat/multilingual-e5-base",
        embedding_dim=768,
        embedding=dummy_vec,
        language="en",
    )
    c_draft = KnowledgeChunk(
        id=c_draft_id,
        document_id=doc_draft.id,
        chunk_index=0,
        content="Draft secret cyber security helpline 1930 details.",
        token_count=10,
        embedding_model="intfloat/multilingual-e5-base",
        embedding_dim=768,
        embedding=dummy_vec,
        language="en",
    )
    c_review = KnowledgeChunk(
        id=c_review_id,
        document_id=doc_review.id,
        chunk_index=0,
        content="Review cyber security helpline 1930 details.",
        token_count=10,
        embedding_model="intfloat/multilingual-e5-base",
        embedding_dim=768,
        embedding=dummy_vec,
        language="en",
    )
    c_archived = KnowledgeChunk(
        id=c_archived_id,
        document_id=doc_archived.id,
        chunk_index=0,
        content="Archived cyber security helpline 1930 details.",
        token_count=10,
        embedding_model="intfloat/multilingual-e5-base",
        embedding_dim=768,
        embedding=dummy_vec,
        language="en",
    )

    db_session.add_all([doc_pub, doc_draft, doc_review, doc_archived])
    db_session.add_all([c_pub, c_draft, c_review, c_archived])
    await db_session.commit()

    retriever = HybridRetriever(session=db_session, embedder=embedder)
    evidence = await retriever.retrieve("helpline 1930 details")

    retrieved_chunk_ids = [c.chunk_id for c in evidence.chunks]
    assert str(c_pub_id) in retrieved_chunk_ids
    assert str(c_draft_id) not in retrieved_chunk_ids
    assert str(c_review_id) not in retrieved_chunk_ids
    assert str(c_archived_id) not in retrieved_chunk_ids


@pytest.mark.asyncio
async def test_retriever_model_mismatch_excluded(db_session):
    """Verify chunks with a different embedding model are never returned."""
    import uuid

    doc = KnowledgeDocument(
        id=uuid.uuid4(),
        title="Model Check",
        publisher="RBI",
        source_url="https://rbi.org.in/model",
        language="en",
        doc_type="policy",
        version="1.0",
        status="published",
        licence_note="Public Domain",
    )
    embedder = FakeEmbedder()
    vec = embedder.embed_passage("content")

    c_valid_id = uuid.uuid4()
    c_mismatched_id = uuid.uuid4()

    c_valid = KnowledgeChunk(
        id=c_valid_id,
        document_id=doc.id,
        chunk_index=0,
        content="Valid model cyber fraud awareness content.",
        token_count=10,
        embedding_model="intfloat/multilingual-e5-base",
        embedding_dim=768,
        embedding=vec,
        language="en",
    )
    c_mismatched = KnowledgeChunk(
        id=c_mismatched_id,
        document_id=doc.id,
        chunk_index=1,
        content="Mismatched old model cyber fraud awareness content.",
        token_count=10,
        embedding_model="text-embedding-ada-002",
        embedding_dim=768,
        embedding=vec,
        language="en",
    )

    db_session.add(doc)
    db_session.add_all([c_valid, c_mismatched])
    await db_session.commit()

    retriever = HybridRetriever(session=db_session, embedder=embedder)
    evidence = await retriever.retrieve("cyber fraud awareness")

    retrieved_chunk_ids = [c.chunk_id for c in evidence.chunks]
    assert str(c_valid_id) in retrieved_chunk_ids
    assert str(c_mismatched_id) not in retrieved_chunk_ids


@pytest.mark.asyncio
async def test_retrieval_degraded_fallback_handling():
    """Verify graceful degradation when one search modality fails, and error when both fail."""
    mock_session = AsyncMock()
    embedder = FakeEmbedder()
    retriever = HybridRetriever(session=mock_session, embedder=embedder)

    dummy_hit = {
        "chunk_id": "c1",
        "document_id": "d1",
        "chunk_index": 0,
        "title": "T",
        "content": "txt",
        "language": "en",
        "publisher": "P",
        "source_url": "u",
        "version": "1.0",
        "score": 0.9,
    }

    # Case 1: Vector search fails, keyword succeeds
    with (
        patch.object(retriever, "_execute_vector_search", side_effect=Exception("DB vector index timeout")),
        patch.object(retriever, "_execute_keyword_search", return_value=[dummy_hit]),
    ):
        ev = await retriever.retrieve("query")
        assert ev.degraded is True
        assert "VectorSearchFailed" in (ev.degraded_reason or "")
        assert len(ev.chunks) == 1
        assert ev.chunks[0].chunk_id == "c1"

    # Case 2: Keyword search fails, vector succeeds
    with (
        patch.object(retriever, "_execute_vector_search", return_value=[dummy_hit]),
        patch.object(retriever, "_execute_keyword_search", side_effect=Exception("FTS syntax error")),
    ):
        ev = await retriever.retrieve("query")
        assert ev.degraded is True
        assert "KeywordSearchFailed" in (ev.degraded_reason or "")
        assert len(ev.chunks) == 1
        assert ev.chunks[0].chunk_id == "c1"

    # Case 3: Both fail -> raises RetrievalFailedError
    with (
        patch.object(retriever, "_execute_vector_search", side_effect=Exception("Timeout")),
        patch.object(retriever, "_execute_keyword_search", side_effect=Exception("Down")),
    ):
        with pytest.raises(RetrievalFailedError, match="Both search stages failed"):
            await retriever.retrieve("query")
