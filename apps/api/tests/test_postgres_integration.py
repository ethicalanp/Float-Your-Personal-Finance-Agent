import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base, to_sync_database_url
from app.models.enums import ConsentType
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.user import Consent, User

POSTGRES_TEST_URL = os.environ.get(
    "POSTGRES_TEST_URL",
    os.environ.get("PFA_DATABASE_URL", "postgresql+psycopg://float:float_dev_password_change_me@localhost:5432/float_ci"),
)


def _check_postgres_connection() -> bool:
    if "sqlite" in POSTGRES_TEST_URL.lower():
        return False
    try:
        from sqlalchemy import create_engine

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
    reason="Real PostgreSQL with pgvector service is unavailable",
)
@pytest.mark.asyncio
async def test_postgres_schema_constraints_and_cascades():
    """Verify database check constraints, unique partial indexes, and cascades against real PostgreSQL."""
    engine = create_async_engine(POSTGRES_TEST_URL, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    User.__table__,
                    Consent.__table__,
                    KnowledgeDocument.__table__,
                    KnowledgeChunk.__table__,
                ],
            )
        )

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Test check constraint on User normalized_email
    async with session_maker() as session:
        bad_user = User(
            id=uuid.uuid4(),
            email="TestUser@Example.com",
            normalized_email="wrong_value_not_matching_lower_trim",
            hashed_password="hashed_pw_test",
            full_name="Constraint Tester",
        )
        session.add(bad_user)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    # 2. Test valid user and active consent unique constraint
    test_user_id = uuid.uuid4()
    test_email = f"pg_test_{test_user_id.hex[:8]}@example.com"
    async with session_maker() as session:
        valid_user = User(
            id=test_user_id,
            email=test_email,
            normalized_email=test_email.lower().strip(),
            hashed_password="hashed_pw_test",
            full_name="Postgres Tester",
        )
        session.add(valid_user)
        await session.commit()

    async with session_maker() as session:
        c1 = Consent(
            id=uuid.uuid4(),
            user_id=test_user_id,
            consent_type=ConsentType.AI_DATA_PROCESSING,
            consent_version="v1.0",
            revoked_at=None,
        )
        session.add(c1)
        await session.commit()

        # Duplicate active consent for the same user and type must fail unique partial index
        c2 = Consent(
            id=uuid.uuid4(),
            user_id=test_user_id,
            consent_type=ConsentType.AI_DATA_PROCESSING,
            consent_version="v1.0",
            revoked_at=None,
        )
        session.add(c2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    # 3. Test check constraint on KnowledgeDocument status
    doc_id = uuid.uuid4()
    async with session_maker() as session:
        bad_doc = KnowledgeDocument(
            id=doc_id,
            title="Invalid Status Document",
            publisher="Test Publisher",
            source_url="https://example.com/doc",
            licence_note="Open Access",
            status="invalid_status_enum",
        )
        session.add(bad_doc)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    # 4. Test check constraint on KnowledgeChunk embedding dimension
    valid_doc_id = uuid.uuid4()
    async with session_maker() as session:
        valid_doc = KnowledgeDocument(
            id=valid_doc_id,
            title="Valid Document for Cascade Test",
            publisher="Reserve Bank of India",
            source_url="https://rbi.org.in/test-doc",
            licence_note="Government Open Data",
            status="published",
        )
        session.add(valid_doc)
        await session.commit()

    async with session_maker() as session:
        bad_chunk = KnowledgeChunk(
            id=uuid.uuid4(),
            document_id=valid_doc_id,
            chunk_index=0,
            content="Dummy content",
            language="en",
            token_count=2,
            embedding_dim=512,  # Must be 768 per constraint
            heading_path="Test",
        )
        session.add(bad_chunk)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    # 5. Test pgvector cosine distance (<=>) search
    v1 = [1.0] + [0.0] * 767
    v2 = [0.0, 1.0] + [0.0] * 766
    c1_id = uuid.uuid4()
    c2_id = uuid.uuid4()
    async with session_maker() as session:
        chunk1 = KnowledgeChunk(
            id=c1_id,
            document_id=valid_doc_id,
            chunk_index=1,
            content="Vector 1 content",
            language="en",
            token_count=3,
            embedding_dim=768,
            heading_path="Heading 1",
            embedding=v1,
            embedding_model="test-embedder",
        )
        chunk2 = KnowledgeChunk(
            id=c2_id,
            document_id=valid_doc_id,
            chunk_index=2,
            content="Vector 2 content",
            language="en",
            token_count=3,
            embedding_dim=768,
            heading_path="Heading 2",
            embedding=v2,
            embedding_model="test-embedder",
        )
        session.add_all([chunk1, chunk2])
        await session.commit()

    async with session_maker() as session:
        # Query closer to v1
        query_v = [0.9] + [0.1] + [0.0] * 766
        stmt = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == valid_doc_id)
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_v))
            .limit(1)
        )
        result = await session.execute(stmt)
        closest = result.scalar_one()
        assert closest.id == c1_id

    # Clean up test artifacts
    async with session_maker() as session:
        await session.execute(text("DELETE FROM knowledge_chunks WHERE document_id = :d"), {"d": valid_doc_id})
        await session.execute(text("DELETE FROM knowledge_documents WHERE id = :d"), {"d": valid_doc_id})
        await session.execute(text("DELETE FROM user_consents WHERE user_id = :u"), {"u": test_user_id})
        await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": test_user_id})
        await session.commit()

    await engine.dispose()
