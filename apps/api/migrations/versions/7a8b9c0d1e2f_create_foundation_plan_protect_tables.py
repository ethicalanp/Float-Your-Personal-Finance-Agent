"""Create foundation, plan, and protect tables.

Revision ID: 7a8b9c0d1e2f
Revises: 4f3fa7945abe
Create Date: 2026-11-16 21:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision = "7a8b9c0d1e2f"
down_revision = "4f3fa7945abe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Users Table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_users_email", "users", ["email"])

    # 2. User Consents Table
    op.create_table(
        "user_consents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("terms_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_version", sa.String(length=32), nullable=False, server_default="v1.0"),
        sa.Column("ai_data_processing_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ip_address_mask", sa.String(length=64), nullable=True),
    )

    # 3. Accounts Table
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False, server_default="savings"),
        sa.Column("institution_name", sa.String(length=128), nullable=False, server_default="Bank"),
        sa.Column("account_number_mask", sa.String(length=32), nullable=False, server_default="****0000"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
        sa.Column("current_balance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_accounts_user_id", "accounts", ["user_id"])

    # 4. Transactions Table
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("transaction_type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="Other"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_cleaned", sa.Text(), nullable=False),
        sa.Column("merchant", sa.String(length=128), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="csv_upload"),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_transactions_user_id", "transactions", ["user_id"])
    op.create_index("idx_transactions_account_id", "transactions", ["account_id"])
    op.create_index("idx_transactions_category", "transactions", ["category"])
    op.create_index("idx_transactions_fingerprint", "transactions", ["fingerprint"])
    op.create_index("idx_transactions_user_fingerprint", "transactions", ["user_id", "fingerprint"], unique=True)

    # 5. Scam Check Logs Table
    op.create_table(
        "scam_check_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("message_masked", sa.Text(), nullable=False),
        sa.Column("language_detected", sa.String(length=32), nullable=False, server_default="en"),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("risk_tier", sa.String(length=32), nullable=False, server_default="SAFE"),
        sa.Column("indicators_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_scam", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_feedback_accurate", sa.Boolean(), nullable=True),
        sa.Column("user_feedback_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_scam_check_logs_user_id", "scam_check_logs", ["user_id"])

    # 6. Recovery Cases Table
    op.create_table(
        "recovery_cases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("incident_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("scam_type", sa.String(length=64), nullable=False, server_default="phishing"),
        sa.Column("amount_lost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("platform", sa.String(length=64), nullable=False, server_default="SMS"),
        sa.Column("incident_summary_masked", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="reported"),
        sa.Column("steps_completed_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_recovery_cases_user_id", "recovery_cases", ["user_id"])

    # 7. Scam Samples Table (Daily active learning)
    op.create_table(
        "scam_samples",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("is_scam", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scam_type", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="user_submission"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 8. Audit Trail Table
    op.create_table(
        "audit_trail",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_trail_user_id", "audit_trail", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_trail")
    op.drop_table("scam_samples")
    op.drop_table("recovery_cases")
    op.drop_table("scam_check_logs")
    op.drop_table("transactions")
    op.drop_table("accounts")
    op.drop_table("user_consents")
    op.drop_table("users")
