import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Graceful SQLite compatibility mappings for local development and unit tests
compiles(TSVECTOR, "sqlite")(lambda t, c, **kw: "TEXT")
compiles(Vector, "sqlite")(lambda t, c, **kw: "JSON")
compiles(Computed, "sqlite")(lambda e, c, **kw: "")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("idx_knowledge_documents_publisher_version", "publisher", "version"),
        Index("idx_knowledge_documents_status", "status"),
        Index("idx_knowledge_documents_content_hash", "content_hash"),
        CheckConstraint(
            "status IN ('draft', 'processing', 'review', 'published', 'superseded', 'archived')",
            name="ck_knowledge_documents_status",
        ),
        CheckConstraint(
            "status != 'published' OR ("
            "licence_note IS NOT NULL AND length(trim(licence_note)) > 0 AND "
            "source_url IS NOT NULL AND length(trim(source_url)) > 0)",
            name="ck_knowledge_documents_published_licence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    licence_note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(32), default="1", server_default=text("'1'"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", server_default=text("'draft'"), nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", server_default=text("'en'"), nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(64), default="advisory", server_default=text("'advisory'"), nullable=False
    )
    publication_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunks_document_index"),
        CheckConstraint("embedding_dim = 768", name="ck_knowledge_chunks_embedding_dim"),
        Index(
            "idx_knowledge_chunks_content_tsv",
            "content_tsv",
            postgresql_using="gin",
        ),
        Index(
            "idx_knowledge_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_knowledge_chunks_is_indexable", "is_indexable"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_documents.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", server_default=text("'en'"), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=768, server_default=text("768"), nullable=False)
    heading_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, content)", persisted=True),
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    is_indexable: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
