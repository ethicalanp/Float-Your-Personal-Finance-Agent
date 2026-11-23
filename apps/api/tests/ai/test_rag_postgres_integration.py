import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

POSTGRES_TEST_URL = os.environ.get(
    "POSTGRES_TEST_URL",
    os.environ.get("PFA_DATABASE_URL", "postgresql+psycopg://float:float_dev_password_change_me@localhost:5432/float"),
)


def _check_postgres_connection() -> bool:
    """Synchronously probe whether a real PostgreSQL + pgvector server is reachable."""
    if "sqlite" in POSTGRES_TEST_URL.lower():
        return False
    try:
        from sqlalchemy import create_engine

        from app.db.session import to_sync_database_url

        sync_url = to_sync_database_url(POSTGRES_TEST_URL)
        engine = create_engine(sync_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        engine.dispose()
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _check_postgres_connection()


@pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Real PostgreSQL with pgvector service is unavailable (runs in CI via Docker service)",
)
@pytest.mark.asyncio
async def test_postgres_pgvector_and_trgm_extensions_and_search():
    """Verify vector search, keyword search, and hybrid fusion against real PostgreSQL with pgvector."""
    engine = create_async_engine(POSTGRES_TEST_URL, pool_pre_ping=True)

    async with engine.begin() as conn:
        # 1. Enable required PostgreSQL extensions
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

        # 2. Ensure schema exists
        from app.db.session import Base

        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[KnowledgeDocument.__table__, KnowledgeChunk.__table__],
            )
        )

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        embedder = FakeEmbedder(dimension=768, model_name="intfloat/multilingual-e5-base")
        doc_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        test_doc = KnowledgeDocument(
            id=doc_id,
            title="RBI Cyber Fraud Circular 2026",
            publisher="Reserve Bank of India",
            source_url="https://rbi.org.in/cyber-2026",
            licence_note="Government Open Data",
            version="1.0",
            status="published",
            language="en",
            doc_type="guideline",
            created_at=datetime.now(UTC),
        )

        passage_text = "Call 1930 immediately to freeze unauthorized financial fraud transactions."
        vector_768 = embedder.embed_passage(passage_text)

        test_chunk = KnowledgeChunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            content=passage_text,
            language="en",
            token_count=15,
            embedding_dim=768,
            heading_path="Emergency Measures > Reporting",
            embedding=vector_768,
            embedding_model="intfloat/multilingual-e5-base",
            created_at=datetime.now(UTC),
        )

        session.add(test_doc)
        await session.flush()
        session.add(test_chunk)
        await session.commit()

        try:
            retriever = HybridRetriever(
                session=session,
                embedder=embedder,
                config=RetrievalConfig(embedding_model="intfloat/multilingual-e5-base"),
            )

            # Stage A: Vector Search
            query_vector = embedder.embed_query("How to freeze fraudulent transactions")
            vector_results = await retriever._execute_vector_search(
                query_vector=query_vector,
                limit=100,
                language_filter=None,
                doc_type_filter=None,
            )
            assert len(vector_results) >= 1
            v_hit = next((h for h in vector_results if h["chunk_id"] == str(chunk_id)), None)
            assert v_hit is not None
            assert -1.0 <= v_hit["score"] <= 1.0

            # Stage B: Keyword Search
            keyword_results = await retriever._execute_keyword_search(
                tokens=["1930", "freeze", "fraud"],
                limit=100,
                language_filter=None,
                doc_type_filter=None,
            )
            assert len(keyword_results) >= 1
            k_hit = next((h for h in keyword_results if h["chunk_id"] == str(chunk_id)), None)
            assert k_hit is not None
            assert k_hit["score"] > 0.0

            # Stage C: Hybrid Fusion Path
            evidence = await retriever.retrieve(
                "Call 1930 immediately to freeze unauthorized financial fraud transactions"
            )
            assert evidence.degraded is False
            assert len(evidence.chunks) >= 1
            assert any("1930" in c.text for c in evidence.chunks)

        finally:
            # Clean up test rows
            await session.delete(test_chunk)
            await session.delete(test_doc)
            await session.commit()

    await engine.dispose()
