"""Add extended auth models, session tracking, token rotation, and identities.

Revision ID: a2b3c4d5e6f7
Revises: e6f7a8b9c0d1
Create Date: 2026-11-25 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Update consent_type enum if in PostgreSQL and create new enums idempotently
    if is_postgres:
        op.execute("ALTER TYPE consent_type ADD VALUE IF NOT EXISTS 'privacy';")
        op.execute(
            "DO $$ BEGIN CREATE TYPE auth_provider AS ENUM ('password', 'google', 'phone'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$;"
        )
        op.execute(
            "DO $$ BEGIN CREATE TYPE auth_token_type AS ENUM ('otp', 'email_verification', 'password_reset'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$;"
        )
        op.execute(
            """DO $$ BEGIN
                CREATE TYPE auth_audit_event_type AS ENUM (
                    'register', 'login_success', 'login_failure', 'otp_request',
                    'otp_verify_success', 'otp_verify_failure', 'password_reset_request',
                    'password_reset_success', 'email_verify_request', 'email_verify_success',
                    'refresh_success', 'refresh_reuse_detected', 'logout', 'logout_all',
                    'identity_linked', 'identity_unlinked'
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;"""
        )

    # 2. Enum descriptors with create_type=False so create_table does not re-issue CREATE TYPE
    auth_provider_enum = sa.Enum(
        "password", "google", "phone", name="auth_provider", create_type=False
    )
    auth_token_type_enum = sa.Enum(
        "otp", "email_verification", "password_reset", name="auth_token_type", create_type=False
    )
    auth_audit_event_enum = sa.Enum(
        "register",
        "login_success",
        "login_failure",
        "otp_request",
        "otp_verify_success",
        "otp_verify_failure",
        "password_reset_request",
        "password_reset_success",
        "email_verify_request",
        "email_verify_success",
        "refresh_success",
        "refresh_reuse_detected",
        "logout",
        "logout_all",
        "identity_linked",
        "identity_unlinked",
        name="auth_audit_event_type",
        create_type=False,
    )

    # 3. Alter users table
    op.alter_column("users", "hashed_password", nullable=True)
    op.alter_column("users", "email", nullable=True)
    op.alter_column("users", "normalized_email", nullable=True)
    op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))
    op.create_unique_constraint("uq_users_phone_number", "users", ["phone_number"])

    if is_postgres:
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_normalized_email;")
        op.execute(
            "ALTER TABLE users ADD CONSTRAINT ck_users_normalized_email "
            "CHECK (normalized_email IS NULL OR normalized_email = lower(trim(email)));"
        )
        op.execute(
            "ALTER TABLE users ADD CONSTRAINT ck_users_email_or_phone "
            "CHECK (email IS NOT NULL OR phone_number IS NOT NULL);"
        )

    # 4. Create user_identities table
    op.create_table(
        "user_identities",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", auth_provider_enum, nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_user_identities_provider_uid"),
    )
    op.create_index("idx_user_identities_user_id", "user_identities", ["user_id"])

    # 5. Create user_sessions table
    op.create_table(
        "user_sessions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_family_id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "is_revoked",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address_mask", sa.String(length=64), nullable=True),
    )
    op.create_index("idx_user_sessions_user_revoked", "user_sessions", ["user_id", "is_revoked"])
    op.create_index("idx_user_sessions_family", "user_sessions", ["session_family_id"])

    # 6. Create auth_tokens table
    op.create_table(
        "auth_tokens",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", auth_token_type_enum, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
        sa.Column(
            "is_used",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_auth_tokens_lookup", "auth_tokens", ["identifier_hash", "token_type", "is_used"])

    # 7. Create auth_audit_logs table
    op.create_table(
        "auth_audit_logs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", auth_audit_event_enum, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("identifier_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_address_mask", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_auth_audit_logs_event_time", "auth_audit_logs", ["event_type", "created_at"])
    op.create_index("idx_auth_audit_logs_identifier", "auth_audit_logs", ["identifier_hash"])


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_table("auth_audit_logs")
    op.drop_table("auth_tokens")
    op.drop_table("user_sessions")
    op.drop_table("user_identities")

    if is_postgres:
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_email_or_phone;")
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_normalized_email;")
        op.execute(
            "ALTER TABLE users ADD CONSTRAINT ck_users_normalized_email "
            "CHECK (normalized_email = lower(trim(email)));"
        )

    op.drop_constraint("uq_users_phone_number", "users", type_="unique")
    op.drop_column("users", "phone_number")
    op.alter_column("users", "normalized_email", nullable=False)
    op.alter_column("users", "email", nullable=False)
    op.alter_column("users", "hashed_password", nullable=False)

    if is_postgres:
        sa.Enum(name="auth_audit_event_type").drop(bind, checkfirst=True)
        sa.Enum(name="auth_token_type").drop(bind, checkfirst=True)
        sa.Enum(name="auth_provider").drop(bind, checkfirst=True)
