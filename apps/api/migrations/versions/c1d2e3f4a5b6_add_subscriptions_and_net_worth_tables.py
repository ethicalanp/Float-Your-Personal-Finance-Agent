"""Add subscription leak decisions and net worth tables.

Revision ID: c1d2e3f4a5b6
Revises: a9b8c7d6e5f4
Create Date: 2026-11-27 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscription_leak_decisions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("leak_key", sa.String(length=160), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decision IN ('keep', 'cancel')", name="ck_sub_leak_decision"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "leak_key", name="uq_sub_leak_user_key"),
    )
    op.create_index(
        op.f("ix_subscription_leak_decisions_user_id"),
        "subscription_leak_decisions",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "net_worth_items",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("item_type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), server_default=sa.text("'other'"), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("valued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("item_type IN ('asset', 'liability')", name="ck_nw_item_type"),
        sa.CheckConstraint("amount_paise >= 0", name="ck_nw_amount_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_net_worth_items_user_id"), "net_worth_items", ["user_id"], unique=False)

    op.create_table(
        "net_worth_snapshots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_assets_paise", sa.BigInteger(), nullable=False),
        sa.Column("total_liabilities_paise", sa.BigInteger(), nullable=False),
        sa.Column("net_worth_paise", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_net_worth_snapshots_user_id"), "net_worth_snapshots", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_net_worth_snapshots_user_id"), table_name="net_worth_snapshots")
    op.drop_table("net_worth_snapshots")
    op.drop_index(op.f("ix_net_worth_items_user_id"), table_name="net_worth_items")
    op.drop_table("net_worth_items")
    op.drop_index(op.f("ix_subscription_leak_decisions_user_id"), table_name="subscription_leak_decisions")
    op.drop_table("subscription_leak_decisions")
