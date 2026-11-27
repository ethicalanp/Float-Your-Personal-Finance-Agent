"""Add budget_plans table and recurring enhancements.

Revision ID: a9b8c7d6e5f4
Revises: f7a8b9c0d1e2
Create Date: 2026-11-27 09:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9b8c7d6e5f4"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budget_plans",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("monthly_income_paise", sa.BigInteger(), nullable=False),
        sa.Column("extra_income_paise", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("income_mode", sa.String(length=32), server_default=sa.text("'fixed'"), nullable=False),
        sa.Column("irregular_months", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("needs_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("wants_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("savings_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("needs_paise", sa.BigInteger(), nullable=False),
        sa.Column("wants_paise", sa.BigInteger(), nullable=False),
        sa.Column("savings_paise", sa.BigInteger(), nullable=False),
        sa.Column("category_mappings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("monthly_income_paise > 0", name="ck_budget_plan_income_positive"),
        sa.CheckConstraint("extra_income_paise >= 0", name="ck_budget_plan_extra_income_nonnegative"),
        sa.CheckConstraint(
            "needs_pct >= 0 AND wants_pct >= 0 AND savings_pct >= 0",
            name="ck_budget_plan_pct_nonnegative",
        ),
        sa.CheckConstraint(
            "needs_paise >= 0 AND wants_paise >= 0 AND savings_paise >= 0",
            name="ck_budget_plan_paise_nonnegative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "month", "version", name="uq_budget_plan_user_month_version"),
    )
    op.create_index(
        "idx_budget_plan_user_month_current",
        "budget_plans",
        ["user_id", "month", "is_current"],
        unique=False,
    )

    op.add_column("recurring_commitments", sa.Column("merchant_keywords", sa.JSON(), nullable=True))
    op.add_column("recurring_commitments", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("recurring_commitments", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column(
        "recurring_commitments",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )

    op.add_column("recurring_occurrences", sa.Column("match_reason", sa.String(length=255), nullable=True))
    op.add_column("recurring_occurrences", sa.Column("mismatch_flag", sa.String(length=64), nullable=True))
    op.add_column("recurring_occurrences", sa.Column("mismatch_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("recurring_occurrences", "mismatch_reason")
    op.drop_column("recurring_occurrences", "mismatch_flag")
    op.drop_column("recurring_occurrences", "match_reason")

    op.drop_column("recurring_commitments", "version")
    op.drop_column("recurring_commitments", "end_date")
    op.drop_column("recurring_commitments", "start_date")
    op.drop_column("recurring_commitments", "merchant_keywords")

    op.drop_index("idx_budget_plan_user_month_current", table_name="budget_plans")
    op.drop_table("budget_plans")
