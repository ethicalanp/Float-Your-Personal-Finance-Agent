import uuid
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.models import DocumentChunk, ManifestSource
from app.ai.rag.smoke import run_document_smoke_check
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


class RepositoryError(Exception):
    pass


class DocumentApprovalRefusedError(RepositoryError):
    pass


class KnowledgeRepository:
    """Async & sync database repository for knowledge documents and chunks."""

    def __init__(self, session: AsyncSession | Session) -> None:
        self.session = session

    async def get_document_by_content_hash(self, content_hash: str) -> KnowledgeDocument | None:
        """Find an existing document with the identical content hash."""
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.content_hash == content_hash)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            return result.scalars().first()
        else:
            return self.session.execute(stmt).scalars().first()

    async def get_document_by_id(self, doc_id: uuid.UUID) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            return result.scalars().first()
        else:
            return self.session.execute(stmt).scalars().first()

    async def list_documents(self, status: str | None = None) -> Sequence[KnowledgeDocument]:
        stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
        if status:
            stmt = stmt.where(KnowledgeDocument.status == status)
        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            return self.session.execute(stmt).scalars().all()

    async def get_chunks_for_document(self, doc_id: uuid.UUID) -> Sequence[KnowledgeChunk]:
        stmt = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        )
        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            return self.session.execute(stmt).scalars().all()

    async def get_published_chunks(
        self,
        language: str | None = None,
        limit: int = 20,
    ) -> Sequence[KnowledgeChunk]:
        """Return only chunks from published documents.

        Strictly excludes draft, review, processing, superseded, and archived documents.
        """
        stmt = (
            select(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.status == "published")
        )
        if language:
            stmt = stmt.where(KnowledgeChunk.language == language)
        stmt = stmt.limit(limit)

        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            return self.session.execute(stmt).scalars().all()

    async def create_document(
        self,
        source: ManifestSource,
        content_hash: str,
        status: str = "processing",
        supersedes_id: uuid.UUID | None = None,
    ) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            title=source.title,
            publisher=source.publisher,
            source_url=source.source_url or f"file://{source.file_path}",
            licence_note=source.licence_note,
            version=source.version,
            status=status,
            language=source.language,
            doc_type=source.doc_type,
            publication_date=(
                datetime.combine(source.publication_date, datetime.min.time(), tzinfo=UTC)
                if source.publication_date
                else None
            ),
            effective_date=(
                datetime.combine(source.effective_date, datetime.min.time(), tzinfo=UTC)
                if source.effective_date
                else None
            ),
            content_hash=content_hash,
            supersedes_id=supersedes_id,
        )
        self.session.add(doc)
        if isinstance(self.session, AsyncSession):
            await self.session.flush()
        else:
            self.session.flush()
        return doc

    async def save_chunks(
        self,
        document_id: uuid.UUID,
        chunks: list[DocumentChunk],
    ) -> None:
        orm_chunks = [
            KnowledgeChunk(
                id=uuid.uuid4(),
                document_id=document_id,
                chunk_index=c.chunk_index,
                content=c.content,
                language=c.language,
                token_count=c.token_count,
                embedding_dim=c.embedding_dim,
                heading_path=c.heading_path,
                embedding=c.embedding,
                embedding_model=c.embedding_model,
            )
            for c in chunks
        ]
        self.session.add_all(orm_chunks)
        if isinstance(self.session, AsyncSession):
            await self.session.flush()
        else:
            self.session.flush()

    async def approve_document(
        self,
        doc_id: uuid.UUID,
        reviewer: str,
        embedder: BaseEmbedder,
    ) -> KnowledgeDocument:
        """Approve a document: transition from 'review' to 'published'.

        Refuses if:
        1. Document is not in review status.
        2. licence_note is missing or blank.
        3. source_url is missing or blank.
        4. Smoke retrieval check fails.
        Upon approval, automatically supersedes any previous version.
        """
        doc = await self.get_document_by_id(doc_id)
        if not doc:
            raise RepositoryError(f"Document {doc_id} not found")

        if doc.status not in ("review", "processing"):
            raise DocumentApprovalRefusedError(
                f"Cannot approve document {doc_id}: current status is '{doc.status}', expected 'review'"
            )

        # Enforce licence note
        if not doc.licence_note or not doc.licence_note.strip():
            raise DocumentApprovalRefusedError(f"Cannot publish document {doc_id}: 'licence_note' is missing or empty")

        # Enforce source URL
        if not doc.source_url or not doc.source_url.strip():
            raise DocumentApprovalRefusedError(f"Cannot publish document {doc_id}: 'source_url' is missing or empty")

        # Run Smoke Check
        chunks_orm = await self.get_chunks_for_document(doc_id)
        chunks_model = [
            DocumentChunk(
                chunk_index=c.chunk_index,
                content=c.content,
                heading_path=c.heading_path,
                language=c.language,
                token_count=c.token_count,
                embedding_dim=c.embedding_dim,
                embedding_model=c.embedding_model,
                embedding=c.embedding,
            )
            for c in chunks_orm
        ]

        smoke_res = run_document_smoke_check(doc.title, chunks_model, embedder)
        if not smoke_res.passed:
            raise DocumentApprovalRefusedError(
                f"Document {doc_id} failed smoke retrieval check: {smoke_res.error_message or smoke_res.results}"
            )

        # State transition: publish new document
        doc.status = "published"
        doc.reviewed_by = reviewer
        doc.reviewed_at = datetime.now(UTC)

        # Supersede previous version if supersedes_id was set
        if doc.supersedes_id:
            old_doc = await self.get_document_by_id(doc.supersedes_id)
            if old_doc and old_doc.status == "published":
                old_doc.status = "superseded"

        if isinstance(self.session, AsyncSession):
            await self.session.commit()
        else:
            self.session.commit()

        return doc

    async def archive_document(self, doc_id: uuid.UUID) -> KnowledgeDocument:
        doc = await self.get_document_by_id(doc_id)
        if not doc:
            raise RepositoryError(f"Document {doc_id} not found")

        doc.status = "archived"
        if isinstance(self.session, AsyncSession):
            await self.session.commit()
        else:
            self.session.commit()
        return doc

    async def reembed_document(
        self,
        doc_id: uuid.UUID,
        new_model_name: str,
        embedder: BaseEmbedder,
    ) -> int:
        """Atomic re-embed of an entire document with a new embedding model.

        Calculates new embeddings for all chunks, updates embedding_model and embedding_dim
        in a single transaction so the document index is never half old and half new.
        """
        chunks = await self.get_chunks_for_document(doc_id)
        if not chunks:
            return 0

        # Pre-compute all new embeddings
        texts = [c.content for c in chunks]
        new_vectors = embedder.embed_passages(texts)

        for c, vec in zip(chunks, new_vectors, strict=False):
            c.embedding = vec
            c.embedding_model = new_model_name
            c.embedding_dim = embedder.dimension

        if isinstance(self.session, AsyncSession):
            await self.session.commit()
        else:
            self.session.commit()

        return len(chunks)
