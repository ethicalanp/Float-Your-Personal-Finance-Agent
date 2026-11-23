"""Expand knowledge documents and chunks schema for RAG lifecycle and multilingual search.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-22 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind and bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    inspector = sa.inspect(bind)
    doc_cols = {c["name"] for c in inspector.get_columns("knowledge_documents")}
    chunk_cols = {c["name"] for c in inspector.get_columns("knowledge_chunks")}
    doc_indexes = {idx["name"] for idx in inspector.get_indexes("knowledge_documents")}

    # 1. Expand knowledge_documents
    if "status" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        )
    if "language" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("language", sa.String(length=16), server_default="en", nullable=False),
        )
    if "doc_type" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("doc_type", sa.String(length=64), server_default="advisory", nullable=False),
        )
    if "publication_date" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
        )
    if "effective_date" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        )
    if "content_hash" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("content_hash", sa.String(length=64), nullable=True),
        )
    if "reviewed_by" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        )
    if "reviewed_at" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "supersedes_id" not in doc_cols:
        op.add_column(
            "knowledge_documents",
            sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        )
        op.create_foreign_key(
            "fk_knowledge_documents_supersedes_id",
            "knowledge_documents",
            "knowledge_documents",
            ["supersedes_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if "idx_knowledge_documents_status" not in doc_indexes:
        op.create_index("idx_knowledge_documents_status", "knowledge_documents", ["status"])
    if "idx_knowledge_documents_content_hash" not in doc_indexes:
        op.create_index("idx_knowledge_documents_content_hash", "knowledge_documents", ["content_hash"])

    if is_postgres:
        doc_constraints = {c["name"] for c in inspector.get_check_constraints("knowledge_documents")}
        if "ck_knowledge_documents_status" not in doc_constraints:
            op.create_check_constraint(
                "ck_knowledge_documents_status",
                "knowledge_documents",
                "status IN ('draft', 'processing', 'review', 'published', 'superseded', 'archived')",
            )
        if "ck_knowledge_documents_published_licence" not in doc_constraints:
            op.create_check_constraint(
                "ck_knowledge_documents_published_licence",
                "knowledge_documents",
                "status != 'published' OR (licence_note IS NOT NULL AND length(trim(licence_note)) > 0 "
                "AND source_url IS NOT NULL AND length(trim(source_url)) > 0)",
            )

    # 2. Expand knowledge_chunks
    if "language" not in chunk_cols:
        op.add_column(
            "knowledge_chunks",
            sa.Column("language", sa.String(length=16), server_default="en", nullable=False),
        )
    if "token_count" not in chunk_cols:
        op.add_column(
            "knowledge_chunks",
            sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        )
    if "embedding_dim" not in chunk_cols:
        op.add_column(
            "knowledge_chunks",
            sa.Column("embedding_dim", sa.Integer(), server_default="768", nullable=False),
        )
    if "heading_path" not in chunk_cols:
        op.add_column(
            "knowledge_chunks",
            sa.Column("heading_path", sa.Text(), nullable=True),
        )

    if is_postgres:
        chunk_constraints = {c["name"] for c in inspector.get_check_constraints("knowledge_chunks")}
        if "ck_knowledge_chunks_embedding_dim" not in chunk_constraints:
            op.create_check_constraint(
                "ck_knowledge_chunks_embedding_dim",
                "knowledge_chunks",
                "embedding_dim = 768",
            )
        # Recreate content_tsv with 'simple' regconfig for multilingual Malayalam/Manglish/English
        op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_content_tsv")
        op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS content_tsv")
        op.execute(
            "ALTER TABLE knowledge_chunks ADD COLUMN content_tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content)) STORED"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_content_tsv ON knowledge_chunks USING gin (content_tsv)"
        )

        # 3. Create published chunks view
        op.execute(
            """
            CREATE OR REPLACE VIEW published_knowledge_chunks AS
            SELECT c.*
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON c.document_id = d.id
            WHERE d.status = 'published';
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind and bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    if is_postgres:
        op.execute("DROP VIEW IF EXISTS published_knowledge_chunks")
        op.drop_constraint("ck_knowledge_chunks_embedding_dim", "knowledge_chunks", type_="check")
        op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_content_tsv")
        op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS content_tsv")
        op.execute(
            "ALTER TABLE knowledge_chunks ADD COLUMN content_tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('english'::regconfig, content)) STORED"
        )
        op.execute(
            "CREATE INDEX idx_knowledge_chunks_content_tsv ON knowledge_chunks USING gin (content_tsv)"
        )
        op.drop_constraint("ck_knowledge_documents_published_licence", "knowledge_documents", type_="check")
        op.drop_constraint("ck_knowledge_documents_status", "knowledge_documents", type_="check")

    op.drop_column("knowledge_chunks", "heading_path")
    op.drop_column("knowledge_chunks", "embedding_dim")
    op.drop_column("knowledge_chunks", "token_count")
    op.drop_column("knowledge_chunks", "language")

    op.drop_index("idx_knowledge_documents_content_hash", table_name="knowledge_documents")
    op.drop_index("idx_knowledge_documents_status", table_name="knowledge_documents")
    op.drop_constraint("fk_knowledge_documents_supersedes_id", "knowledge_documents", type_="foreignkey")

    op.drop_column("knowledge_documents", "supersedes_id")
    op.drop_column("knowledge_documents", "reviewed_at")
    op.drop_column("knowledge_documents", "reviewed_by")
    op.drop_column("knowledge_documents", "content_hash")
    op.drop_column("knowledge_documents", "effective_date")
    op.drop_column("knowledge_documents", "publication_date")
    op.drop_column("knowledge_documents", "doc_type")
    op.drop_column("knowledge_documents", "language")
    op.drop_column("knowledge_documents", "status")
