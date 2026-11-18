"""Upgrade the foundation schema to the hardened DBML v2 design.

Revision ID: b3c4d5e6f708
Revises: 7a8b9c0d1e2f
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from alembic import op

from app.models import Base
from app.models.enums import (
    AccountStatus,
    AccountType,
    AuditActor,
    CaseStatus,
    ConsentType,
    ImportStatus,
    LanguageCode,
    MessageRole,
    ReadinessBand,
    RiskTier,
    TransactionSource,
    TransactionType,
    enum_type,
)

revision = "b3c4d5e6f708"
down_revision = "7a8b9c0d1e2f"
branch_labels = None
depends_on = None


_ENUM_TYPES = (
    enum_type(AccountStatus, "account_status"),
    enum_type(AccountType, "account_type"),
    enum_type(AuditActor, "audit_actor"),
    enum_type(CaseStatus, "case_status"),
    enum_type(ConsentType, "consent_type"),
    enum_type(ImportStatus, "import_status"),
    enum_type(LanguageCode, "language_code"),
    enum_type(MessageRole, "message_role"),
    enum_type(ReadinessBand, "readiness_band"),
    enum_type(RiskTier, "risk_tier"),
    enum_type(TransactionSource, "txn_source"),
    enum_type(TransactionType, "txn_type"),
)

_LEGACY_TABLES = (
    "users",
    "accounts",
    "transactions",
    "scam_check_logs",
    "recovery_cases",
    "scam_samples",
    "audit_trail",
)


def _validate_legacy_data() -> None:
    op.execute(
        """
        DO $migration$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM users
                GROUP BY lower(btrim(email))
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot normalize users.email: duplicate lower(trim(email)) values exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM accounts
                WHERE length(btrim(currency)) NOT BETWEEN 1 AND 3
            ) THEN
                RAISE EXCEPTION
                    'Cannot convert accounts.currency to CHAR(3): value exceeds three characters';
            END IF;
            IF EXISTS (SELECT 1 FROM transactions WHERE amount <= 0) THEN
                RAISE EXCEPTION
                    'Cannot add ck_transactions_amount_positive: non-positive amounts exist';
            END IF;
            IF EXISTS (SELECT 1 FROM scam_check_logs WHERE risk_score < 0 OR risk_score > 100) THEN
                RAISE EXCEPTION
                    'Cannot add ck_scam_risk_score_range: risk scores outside 0..100 exist';
            END IF;
            IF EXISTS (SELECT 1 FROM recovery_cases WHERE amount_lost < 0) THEN
                RAISE EXCEPTION
                    'Cannot add ck_recovery_amount_lost_nonnegative: negative amounts exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM recovery_cases
                WHERE user_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot make recovery_cases.user_id required: NULL values exist';
            END IF;
        END
        $migration$;
        """
    )


def _hash_scam_samples() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            "SELECT 1 FROM scam_samples GROUP BY text HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot assign unique scam sample text hashes: duplicate sample text "
            "exists. Reconcile duplicate samples before retrying this migration."
        )

    last_id = None
    while True:
        if last_id is None:
            result = bind.execute(
                sa.text("SELECT id, text FROM scam_samples ORDER BY id LIMIT 500")
            )
        else:
            result = bind.execute(
                sa.text(
                    "SELECT id, text FROM scam_samples WHERE id > :last_id "
                    "ORDER BY id LIMIT 500"
                ),
                {"last_id": last_id},
            )
        rows = result.fetchall()
        result.close()
        if not rows:
            break
        parameters = [
            {
                "sample_id": row.id,
                "text_hash": hashlib.sha256(row.text.encode("utf-8")).hexdigest(),
            }
            for row in rows
        ]
        bind.execute(
            sa.text("UPDATE scam_samples SET text_hash = :text_hash WHERE id = :sample_id"),
            parameters,
        )
        last_id = rows[-1].id


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _validate_legacy_data()

    for enum in _ENUM_TYPES:
        enum.create(bind, checkfirst=True)

    op.execute("ALTER TABLE user_consents DROP CONSTRAINT user_consents_user_id_fkey")
    op.execute("ALTER TABLE user_consents DROP CONSTRAINT user_consents_user_id_key")
    op.execute("ALTER TABLE user_consents RENAME TO user_consents_legacy")
    op.execute("ALTER TABLE users DROP CONSTRAINT users_email_key")

    for index_name in (
        "idx_users_email",
        "idx_accounts_user_id",
        "idx_transactions_user_id",
        "idx_transactions_account_id",
        "idx_transactions_category",
        "idx_transactions_fingerprint",
        "idx_transactions_user_fingerprint",
        "idx_scam_check_logs_user_id",
        "idx_recovery_cases_user_id",
        "idx_audit_trail_user_id",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index_name}")

    op.execute("ALTER TABLE transactions DROP CONSTRAINT transactions_account_id_fkey")

    uuid_columns = (
        ("users", "id"),
        ("accounts", "id"),
        ("accounts", "user_id"),
        ("transactions", "id"),
        ("transactions", "account_id"),
        ("transactions", "user_id"),
        ("scam_check_logs", "id"),
        ("scam_check_logs", "user_id"),
        ("recovery_cases", "id"),
        ("recovery_cases", "user_id"),
        ("scam_samples", "id"),
        ("audit_trail", "id"),
        ("audit_trail", "user_id"),
    )
    for table_name, column_name in uuid_columns:
        op.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN {column_name} "
            f"TYPE uuid USING {column_name}::uuid"
        )

    op.add_column("users", sa.Column("normalized_email", sa.String(255)))
    op.execute("UPDATE users SET normalized_email = lower(btrim(email))")
    op.alter_column("users", "normalized_email", nullable=False)
    op.execute("ALTER TABLE users ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.create_check_constraint(
        "ck_users_normalized_email", "users", "normalized_email = lower(btrim(email))"
    )
    op.create_unique_constraint("users_normalized_email_key", "users", ["normalized_email"])

    op.execute("ALTER TABLE accounts ALTER COLUMN account_type DROP DEFAULT")
    op.execute("ALTER TABLE accounts ALTER COLUMN current_balance DROP DEFAULT")
    op.execute("ALTER TABLE accounts ALTER COLUMN account_type TYPE account_type USING account_type::account_type")
    op.execute("ALTER TABLE accounts ALTER COLUMN account_type SET DEFAULT 'savings'")
    op.execute("ALTER TABLE accounts RENAME COLUMN current_balance TO reported_balance")
    op.execute(
        "ALTER TABLE accounts ALTER COLUMN reported_balance TYPE numeric(14,2) "
        "USING reported_balance::numeric(14,2)"
    )
    op.execute("ALTER TABLE accounts ALTER COLUMN currency DROP DEFAULT")
    op.execute(
        "ALTER TABLE accounts ALTER COLUMN currency TYPE char(3) USING currency::char(3)"
    )
    op.execute(
        """
        ALTER TABLE accounts
            ADD COLUMN status account_status NOT NULL DEFAULT 'active',
            ADD COLUMN reported_balance_at timestamptz,
            ADD COLUMN closed_at timestamptz,
            ALTER COLUMN id SET DEFAULT gen_random_uuid(),
            ALTER COLUMN account_type SET NOT NULL,
            ALTER COLUMN currency SET DEFAULT 'INR',
            ALTER COLUMN reported_balance SET DEFAULT 0,
            ALTER COLUMN institution_name DROP DEFAULT,
            ALTER COLUMN account_number_mask DROP DEFAULT;
        """
    )

    op.execute("ALTER TABLE transactions RENAME COLUMN date TO transaction_date")
    op.execute("ALTER TABLE transactions RENAME COLUMN fingerprint TO normalized_fingerprint")
    op.execute("ALTER TABLE transactions ALTER COLUMN source DROP DEFAULT")
    op.execute(
        "ALTER TABLE transactions ALTER COLUMN transaction_type TYPE txn_type "
        "USING transaction_type::txn_type"
    )
    op.execute(
        "ALTER TABLE transactions ALTER COLUMN source TYPE txn_source USING source::txn_source"
    )
    op.execute(
        "ALTER TABLE transactions ALTER COLUMN amount TYPE numeric(14,2) "
        "USING amount::numeric(14,2)"
    )
    op.execute(
        """
        ALTER TABLE transactions
            ADD COLUMN import_id uuid,
            ADD COLUMN normalized_merchant varchar(128),
            ADD COLUMN provider_transaction_id varchar(255),
            ADD COLUMN provider_reference varchar(255),
            ALTER COLUMN id SET DEFAULT gen_random_uuid(),
            ALTER COLUMN category SET DEFAULT 'Other',
            ALTER COLUMN source SET DEFAULT 'csv_upload',
            ALTER COLUMN amount SET NOT NULL,
            ALTER COLUMN normalized_fingerprint TYPE char(64)
                USING normalized_fingerprint::char(64);
        """
    )

    op.execute("ALTER TABLE scam_check_logs ALTER COLUMN language_detected DROP DEFAULT")
    op.execute("ALTER TABLE scam_check_logs ALTER COLUMN risk_tier DROP DEFAULT")
    op.execute("ALTER TABLE scam_check_logs ALTER COLUMN indicators_json DROP DEFAULT")
    op.execute("ALTER TABLE scam_check_logs RENAME COLUMN indicators_json TO indicators")
    op.execute(
        "ALTER TABLE scam_check_logs ALTER COLUMN language_detected TYPE language_code "
        "USING language_detected::language_code"
    )
    op.execute(
        "ALTER TABLE scam_check_logs ALTER COLUMN risk_tier TYPE risk_tier "
        "USING risk_tier::risk_tier"
    )
    op.execute(
        "ALTER TABLE scam_check_logs ALTER COLUMN indicators TYPE jsonb "
        "USING indicators::jsonb"
    )
    op.execute(
        "ALTER TABLE scam_check_logs ALTER COLUMN risk_score TYPE numeric(5,2) "
        "USING risk_score::numeric(5,2)"
    )
    op.execute(
        """
        ALTER TABLE scam_check_logs
            ADD COLUMN model_version varchar(64),
            ALTER COLUMN id SET DEFAULT gen_random_uuid(),
            ALTER COLUMN language_detected SET DEFAULT 'en',
            ALTER COLUMN risk_score SET DEFAULT 0,
            ALTER COLUMN risk_tier SET DEFAULT 'SAFE',
            ALTER COLUMN indicators SET DEFAULT '[]'::jsonb;
        """
    )

    op.execute("ALTER TABLE recovery_cases ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE recovery_cases ALTER COLUMN steps_completed_json DROP DEFAULT")
    op.execute("ALTER TABLE recovery_cases RENAME COLUMN steps_completed_json TO steps_completed")
    op.execute(
        "ALTER TABLE recovery_cases ALTER COLUMN status TYPE case_status "
        "USING status::case_status"
    )
    op.execute(
        "ALTER TABLE recovery_cases ALTER COLUMN steps_completed TYPE jsonb "
        "USING steps_completed::jsonb"
    )
    op.execute(
        "ALTER TABLE recovery_cases ALTER COLUMN amount_lost TYPE numeric(14,2) "
        "USING amount_lost::numeric(14,2)"
    )
    op.execute(
        """
        ALTER TABLE recovery_cases
            ADD COLUMN scam_check_id uuid,
            ADD COLUMN incident_details_encrypted bytea,
            ADD COLUMN encryption_key_version varchar(64),
            ALTER COLUMN id SET DEFAULT gen_random_uuid(),
            ALTER COLUMN status SET DEFAULT 'reported',
            ALTER COLUMN steps_completed SET DEFAULT '[]'::jsonb;
        """
    )

    op.execute(
        """
        ALTER TABLE scam_samples
            ADD COLUMN text_hash char(64),
            ADD COLUMN labeled_by uuid;
        """
    )
    op.execute("ALTER TABLE scam_samples ALTER COLUMN language TYPE language_code USING language::language_code")
    op.execute("ALTER TABLE scam_samples ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    _hash_scam_samples()
    op.execute("ALTER TABLE scam_samples ALTER COLUMN text_hash SET NOT NULL")

    op.execute("ALTER TABLE audit_trail ALTER COLUMN metadata_json DROP DEFAULT")
    op.execute("ALTER TABLE audit_trail RENAME COLUMN metadata_json TO metadata")
    op.execute(
        "ALTER TABLE audit_trail ALTER COLUMN metadata TYPE jsonb USING metadata::jsonb"
    )
    op.execute(
        """
        ALTER TABLE audit_trail
            ADD COLUMN actor audit_actor NOT NULL DEFAULT 'user',
            ALTER COLUMN id SET DEFAULT gen_random_uuid(),
            ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;
        """
    )

    # Create unique parent keys first; the new tables' composite foreign keys need them.
    for table_name in ("accounts", "scam_check_logs"):
        table = Base.metadata.tables[table_name]
        for index in table.indexes:
            if index.unique:
                index.create(bind, checkfirst=True)

    Base.metadata.create_all(bind=bind, checkfirst=True)

    # Existing tables are not changed by create_all, so explicitly install their indexes.
    for table_name in _LEGACY_TABLES:
        table = Base.metadata.tables[table_name]
        for index in table.indexes:
            index.create(bind, checkfirst=True)
    for index in Base.metadata.tables["user_consents"].indexes:
        index.create(bind, checkfirst=True)

    op.create_unique_constraint("scam_samples_text_hash_key", "scam_samples", ["text_hash"])

    op.execute(
        """
        INSERT INTO user_consents
            (id, user_id, consent_type, consent_version, granted_at, ip_address_mask)
        SELECT gen_random_uuid(), user_id::uuid, 'terms', consent_version, consented_at, ip_address_mask
        FROM user_consents_legacy
        WHERE terms_accepted
        """
    )
    op.execute(
        """
        INSERT INTO user_consents
            (id, user_id, consent_type, consent_version, granted_at, ip_address_mask)
        SELECT gen_random_uuid(), user_id::uuid, 'ai_data_processing', consent_version, consented_at, ip_address_mask
        FROM user_consents_legacy
        WHERE ai_data_processing_consent
        """
    )
    op.drop_table("user_consents_legacy")

    op.create_foreign_key("accounts_user_id_fkey", "accounts", "users", ["user_id"], ["id"])
    op.create_foreign_key(
        "transactions_account_id_user_id_fkey",
        "transactions",
        "accounts",
        ["account_id", "user_id"],
        ["id", "user_id"],
    )
    op.create_foreign_key(
        "transactions_import_id_account_id_user_id_fkey",
        "transactions",
        "transaction_imports",
        ["import_id", "account_id", "user_id"],
        ["id", "account_id", "user_id"],
    )
    op.create_foreign_key(
        "scam_check_logs_user_id_fkey", "scam_check_logs", "users", ["user_id"], ["id"]
    )
    op.create_foreign_key(
        "recovery_cases_user_id_fkey", "recovery_cases", "users", ["user_id"], ["id"]
    )
    op.create_foreign_key(
        "recovery_cases_scam_check_id_user_id_fkey",
        "recovery_cases",
        "scam_check_logs",
        ["scam_check_id", "user_id"],
        ["id", "user_id"],
    )
    op.create_foreign_key(
        "scam_samples_labeled_by_fkey", "scam_samples", "users", ["labeled_by"], ["id"]
    )
    op.create_foreign_key("audit_trail_user_id_fkey", "audit_trail", "users", ["user_id"], ["id"])

    for table_name, constraint_name, condition in (
        ("transactions", "ck_transactions_amount_positive", "amount > 0"),
        (
            "scam_check_logs",
            "ck_scam_risk_score_range",
            "risk_score >= 0 AND risk_score <= 100",
        ),
        (
            "recovery_cases",
            "ck_recovery_amount_lost_nonnegative",
            "amount_lost >= 0",
        ),
    ):
        op.create_check_constraint(constraint_name, table_name, condition)


def downgrade() -> None:
    raise RuntimeError(
        "This schema conversion is forward-only because the legacy consent row "
        "cannot losslessly represent consent history. Restore a pre-migration "
        "backup to roll back."
    )
