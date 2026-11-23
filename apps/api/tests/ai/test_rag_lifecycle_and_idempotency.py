from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.models import DocumentChunk, Manifest, ManifestSource
from app.ai.rag.pipeline import run_ingestion_pipeline
from app.ai.rag.repository import DocumentApprovalRefusedError, KnowledgeRepository
from app.db.session import Base
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


@pytest.fixture
async def db_session(tmp_path: Path):
    db_file = tmp_path / "rag_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")

    async with engine.begin() as conn:
        # Create knowledge_documents and knowledge_chunks
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


@pytest.mark.asyncio
async def test_pipeline_idempotency_and_review_state(tmp_path: Path, db_session: AsyncSession) -> None:
    doc_path = tmp_path / "fixture_doc.md"
    doc_path.write_text("# [FIXTURE] Safe Banking Notice\n\nAlways use MFA for transfers.", encoding="utf-8")

    manifest = Manifest(
        sources=[
            ManifestSource(
                id="fixture-safe-banking",
                title="[FIXTURE] Safe Banking Notice",
                publisher="RBI",
                source_url="https://rbi.org.in/safe",
                file_path=str(doc_path),
                language="en",
                licence_note="FIXTURE - Open Public Domain",
            )
        ]
    )
    embedder = FakeEmbedder()

    # Run 1: Should ingest and create document in 'review' state
    report1 = await run_ingestion_pipeline(manifest, embedder, db_session)
    assert report1.documents_new == 1
    assert report1.documents_unchanged == 0
    assert report1.chunks_created >= 1

    repo = KnowledgeRepository(db_session)
    docs = await repo.list_documents()
    assert len(docs) == 1
    assert docs[0].status == "review"
    assert docs[0].content_hash is not None

    # Run 2 with unchanged file: Idempotent no-op
    report2 = await run_ingestion_pipeline(manifest, embedder, db_session)
    assert report2.documents_new == 0
    assert report2.documents_unchanged == 1
    assert report2.chunks_created == 0


@pytest.mark.asyncio
async def test_approval_refusals_and_success(tmp_path: Path, db_session: AsyncSession) -> None:
    embedder = FakeEmbedder()
    repo = KnowledgeRepository(db_session)

    # 1. Document missing licence_note cannot be published
    unlicensed_src = ManifestSource(
        id="fixture-unlicensed",
        title="[FIXTURE] Unlicensed Doc",
        publisher="Test",
        source_url="https://rbi.org.in/unlicensed",
        file_path="dummy.md",
        licence_note=None,
    )
    doc_unlicensed = await repo.create_document(unlicensed_src, content_hash="hash1", status="review")

    with pytest.raises(DocumentApprovalRefusedError, match="'licence_note' is missing or empty"):
        await repo.approve_document(doc_unlicensed.id, reviewer="auditor", embedder=embedder)

    # 2. Valid document with licence passes smoke check and gets published
    valid_src = ManifestSource(
        id="fixture-valid-doc",
        title="[FIXTURE] Valid Banking SOP",
        publisher="RBI",
        source_url="https://rbi.org.in/sop",
        file_path="dummy.md",
        licence_note="FIXTURE - Open Public Domain",
    )
    doc_valid = await repo.create_document(valid_src, content_hash="hash2", status="review")
    # Add sample chunk
    sample_chunks = [
        DocumentChunk(
            chunk_index=0,
            content="Valid Banking SOP details for automated processing.",
            heading_path="Top > SOP",
            language="en",
            token_count=10,
            embedding_dim=768,
            embedding=embedder.embed_passage("Valid Banking SOP details for automated processing."),
        )
    ]
    await repo.save_chunks(doc_valid.id, sample_chunks)

    approved = await repo.approve_document(doc_valid.id, reviewer="lead-auditor", embedder=embedder)
    assert approved.status == "published"
    assert approved.reviewed_by == "lead-auditor"
    assert approved.reviewed_at is not None


@pytest.mark.asyncio
async def test_supersede_lifecycle_and_published_filter(tmp_path: Path, db_session: AsyncSession) -> None:
    embedder = FakeEmbedder()
    repo = KnowledgeRepository(db_session)

    # Version 1: Published
    v1_src = ManifestSource(
        id="fixture-doc-v1",
        title="[FIXTURE] Policy Version 1",
        publisher="RBI",
        source_url="https://rbi.org.in/v1",
        file_path="dummy.md",
        version="1.0",
        licence_note="FIXTURE - Open Public Domain",
    )
    doc_v1 = await repo.create_document(v1_src, content_hash="v1_hash", status="review")
    await repo.save_chunks(
        doc_v1.id,
        [
            DocumentChunk(
                chunk_index=0,
                content="Policy V1 terms.",
                embedding=embedder.embed_passage("Policy V1 terms."),
            )
        ],
    )
    await repo.approve_document(doc_v1.id, reviewer="auditor", embedder=embedder)

    # Verify only published chunks are returned by repository filter
    published_chunks = await repo.get_published_chunks()
    assert len(published_chunks) == 1
    assert published_chunks[0].content == "Policy V1 terms."

    # Version 2: Replaces Version 1
    v2_src = ManifestSource(
        id="fixture-doc-v2",
        title="[FIXTURE] Policy Version 2",
        publisher="RBI",
        source_url="https://rbi.org.in/v2",
        file_path="dummy.md",
        version="2.0",
        licence_note="FIXTURE - Open Public Domain",
    )
    doc_v2 = await repo.create_document(
        v2_src,
        content_hash="v2_hash",
        status="review",
        supersedes_id=doc_v1.id,
    )
    await repo.save_chunks(
        doc_v2.id,
        [
            DocumentChunk(
                chunk_index=0,
                content="Policy V2 terms.",
                embedding=embedder.embed_passage("Policy V2 terms."),
            )
        ],
    )

    # While v2 is in review, published query must STILL only return v1
    chunks_before_v2_pub = await repo.get_published_chunks()
    assert len(chunks_before_v2_pub) == 1
    assert chunks_before_v2_pub[0].content == "Policy V1 terms."

    # Publish Version 2: v1 is automatically marked superseded!
    await repo.approve_document(doc_v2.id, reviewer="auditor", embedder=embedder)

    updated_v1 = await repo.get_document_by_id(doc_v1.id)
    assert updated_v1 is not None
    assert updated_v1.status == "superseded"

    # Now, published query returns ONLY v2 chunks! Superseded v1 chunks are excluded!
    chunks_after_v2_pub = await repo.get_published_chunks()
    assert len(chunks_after_v2_pub) == 1
    assert chunks_after_v2_pub[0].content == "Policy V2 terms."


@pytest.mark.asyncio
async def test_reembed_switch_over(tmp_path: Path, db_session: AsyncSession) -> None:
    embedder_old = FakeEmbedder(dimension=768, model_name="old-model")
    embedder_new = FakeEmbedder(dimension=768, model_name="new-multilingual-model")
    repo = KnowledgeRepository(db_session)

    src = ManifestSource(
        id="fixture-reembed",
        title="[FIXTURE] Re-embed Target",
        publisher="RBI",
        source_url="https://rbi.org.in/reembed",
        file_path="dummy.md",
        licence_note="FIXTURE - Open Public Domain",
    )
    doc = await repo.create_document(src, content_hash="reembed_hash", status="review")
    await repo.save_chunks(
        doc.id,
        [
            DocumentChunk(
                chunk_index=0,
                content="Chunk 1 content",
                embedding=embedder_old.embed_passage("Chunk 1 content"),
                embedding_model="old-model",
            ),
            DocumentChunk(
                chunk_index=1,
                content="Chunk 2 content",
                embedding=embedder_old.embed_passage("Chunk 2 content"),
                embedding_model="old-model",
            ),
        ],
    )

    count = await repo.reembed_document(doc.id, new_model_name="new-multilingual-model", embedder=embedder_new)
    assert count == 2

    chunks = await repo.get_chunks_for_document(doc.id)
    assert len(chunks) == 2
    for c in chunks:
        assert c.embedding_model == "new-multilingual-model"
        assert c.embedding_dim == 768
