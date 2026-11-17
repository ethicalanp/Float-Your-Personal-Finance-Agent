
"""Enable the PostgreSQL pgvector extension."""

from alembic import op

# Revision identifiers.
revision = "4f3fa7945abe"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Enable pgvector for vector similarity search."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Keep the shared database extension installed.

    Removing it could affect other tables or applications
    that depend on pgvector.
    """

