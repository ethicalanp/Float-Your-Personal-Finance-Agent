"""Add user profile preferences and DPDP deletion grace period columns.

Revision ID: 08b1c2d3e4f5
Revises: f7a8b9c0d1e2
Create Date: 2026-11-26 18:35:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "08b1c2d3e4f5"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("users")}

    if "preferred_language" not in cols:
        op.add_column(
            "users",
            sa.Column("preferred_language", sa.String(length=16), server_default=sa.text("'en'"), nullable=False),
        )
    if "locale" not in cols:
        op.add_column(
            "users",
            sa.Column("locale", sa.String(length=16), server_default=sa.text("'en-IN'"), nullable=False),
        )
    if "notification_preferences" not in cols:
        op.add_column(
            "users",
            sa.Column("notification_preferences", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        )
    if "deletion_requested_at" not in cols:
        op.add_column("users", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True))
    if "deletion_scheduled_for" not in cols:
        op.add_column("users", sa.Column("deletion_scheduled_for", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deletion_scheduled_for")
    op.drop_column("users", "deletion_requested_at")
    op.drop_column("users", "notification_preferences")
    op.drop_column("users", "locale")
    op.drop_column("users", "preferred_language")
