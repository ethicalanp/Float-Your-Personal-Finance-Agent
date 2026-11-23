
"""Enable the PostgreSQL pgvector extension."""

from alembic import op

# Revision identifiers.
revision = "4f3fa7945abe"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Enable pgvector and pg_trgm extensions."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    """Keep the shared database extension installed.

    Removing it could affect other tables or applications
    that depend on pgvector.
    """

