"""Add recurring payments commitments, occurrences, and notifications tables.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f708
Create Date: 2026-11-19 14:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f708"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. recurring_commitments
    op.create_table(
        "recurring_commitments",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), server_default="Subscriptions", nullable=False),
        sa.Column("amount_type", sa.String(length=32), server_default="fixed", nullable=False),
        sa.Column("expected_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("min_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("max_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("frequency", sa.String(length=32), server_default="monthly", nullable=False),
        sa.Column("due_rule_day", sa.Integer(), server_default="1", nullable=False),
        sa.Column("merchant", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("origin", sa.String(length=32), server_default="declared", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_recurring_commitments_user", "recurring_commitments", ["user_id", "is_active"])

    # 2. recurring_occurrences
    op.create_table(
        "recurring_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "commitment_id", sa.Uuid(), sa.ForeignKey("recurring_commitments.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("expected_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="upcoming", nullable=False),
        sa.Column(
            "matched_transaction_id", sa.Uuid(), sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("paid_date", sa.Date(), nullable=True),
        sa.Column("paid_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("commitment_id", "due_date", name="uq_commitment_occurrence_due"),
    )
    op.create_index("idx_recurring_occurrences_user_due", "recurring_occurrences", ["user_id", "due_date", "status"])

    # 3. recurring_notifications
    op.create_table(
        "recurring_notifications",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "occurrence_id", sa.Uuid(), sa.ForeignKey("recurring_occurrences.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), server_default="in_app", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message_masked", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "occurrence_id", "notification_type", "channel", name="uq_notification_occurrence_type_channel"
        ),
    )
    op.create_index("idx_notifications_user_sent", "recurring_notifications", ["user_id", "sent_at"])


def downgrade() -> None:
    op.drop_table("recurring_notifications")
    op.drop_table("recurring_occurrences")
    op.drop_table("recurring_commitments")
