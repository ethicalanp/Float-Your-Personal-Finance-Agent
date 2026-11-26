"""Add is_indexable to knowledge_chunks and mark header chunks non-indexable.

Revision ID: f7a8b9c0d1e2
Revises: a2b3c4d5e6f7
Create Date: 2026-11-24 19:50:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    chunk_cols = {c["name"] for c in inspector.get_columns("knowledge_chunks")}
    chunk_indexes = {idx["name"] for idx in inspector.get_indexes("knowledge_chunks")}

    if "is_indexable" not in chunk_cols:
        op.add_column(
            "knowledge_chunks",
            sa.Column(
                "is_indexable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )

    if "idx_knowledge_chunks_is_indexable" not in chunk_indexes:
        op.create_index("idx_knowledge_chunks_is_indexable", "knowledge_chunks", ["is_indexable"])

    # Mark the 8 publisher/advisory document header metadata chunks (chunk_index=0) non-indexable
    op.execute(
        sa.text("""
            UPDATE knowledge_chunks
            SET is_indexable = false
            WHERE chunk_index = 0
              AND (
                content ILIKE '%Publisher%'
                OR content ILIKE '%Advisory ID%'
                OR content ILIKE '%Report Reference%'
                OR content ILIKE '%Target Audience%'
                OR content ILIKE '%Document Title%'
                OR content ILIKE '%Discussion Paper%'
                OR content ILIKE '%Master Direction%'
                OR content ILIKE '%National Strategy%'
              )
        """)
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_chunks_is_indexable", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "is_indexable")
