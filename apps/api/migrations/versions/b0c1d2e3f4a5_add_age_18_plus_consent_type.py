"""Add age_18_plus to consent_type enum.

Revision ID: b0c1d2e3f4a5
Revises: a9b8c7d6e5f4
Create Date: 2026-11-28 12:50:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: str | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE consent_type ADD VALUE IF NOT EXISTS 'age_18_plus'")


def downgrade() -> None:
    # PostgreSQL does not support removing an enum value in-place without recreating the type.
    pass
