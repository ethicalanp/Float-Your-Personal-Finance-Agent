import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import (
    AccountStatus,
    AccountType,
    ImportStatus,
    TransactionSource,
    TransactionType,
    enum_type,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("uq_accounts_id_user", "id", "user_id", unique=True),
        Index("ix_accounts_user_status", "user_id", "status"),
        Index("ix_accounts_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        enum_type(AccountType, "account_type"),
        default=AccountType.SAVINGS,
        server_default=text("'savings'"),
        nullable=False,
    )
    status: Mapped[AccountStatus] = mapped_column(
        enum_type(AccountStatus, "account_status"),
        default=AccountStatus.ACTIVE,
        server_default=text("'active'"),
        nullable=False,
    )
    institution_name: Mapped[str] = mapped_column(String(128), nullable=False)
    account_number_mask: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), default="INR", server_default=text("'INR'"), nullable=False)
    reported_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=text("0"), nullable=False
    )
    reported_balance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class TransactionImport(Base):
    __tablename__ = "transaction_imports"
    __table_args__ = (
        ForeignKeyConstraint(["account_id", "user_id"], ["accounts.id", "accounts.user_id"]),
        Index("idx_import_user_created", "user_id", "created_at"),
        Index("idx_import_account_created", "account_id", "created_at"),
        Index("idx_import_account_user", "account_id", "user_id"),
        Index("uq_import_id_account_user", "id", "account_id", "user_id", unique=True),
        Index(
            "uq_import_file_scope",
            "user_id",
            "account_id",
            "source",
            "file_hash",
            unique=True,
        ),
        Index(
            "uq_import_batch_scope",
            "user_id",
            "account_id",
            "source",
            "source_batch_id",
            unique=True,
        ),
        CheckConstraint("total_parsed >= 0", name="ck_import_total_parsed_nonnegative"),
        CheckConstraint("imported_count >= 0", name="ck_import_imported_count_nonnegative"),
        CheckConstraint("duplicates_skipped >= 0", name="ck_import_duplicates_skipped_nonnegative"),
        CheckConstraint("error_count >= 0", name="ck_import_error_count_nonnegative"),
        CheckConstraint("retry_count >= 0", name="ck_import_retry_count_nonnegative"),
        CheckConstraint(
            "imported_count + duplicates_skipped + error_count <= total_parsed",
            name="ck_import_counts_within_total",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source: Mapped[TransactionSource] = mapped_column(enum_type(TransactionSource, "txn_source"), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        enum_type(ImportStatus, "import_status"),
        default=ImportStatus.QUEUED,
        server_default=text("'queued'"),
        nullable=False,
    )
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(CHAR(64))
    source_batch_id: Mapped[str | None] = mapped_column(String(128))
    total_parsed: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    imported_count: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    error_count: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(default=0, server_default=text("0"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        ForeignKeyConstraint(["account_id", "user_id"], ["accounts.id", "accounts.user_id"]),
        ForeignKeyConstraint(
            ["import_id", "account_id", "user_id"],
            ["transaction_imports.id", "transaction_imports.account_id", "transaction_imports.user_id"],
        ),
        Index("idx_txn_account_date", "account_id", "transaction_date"),
        Index("idx_txn_user_date", "user_id", "transaction_date"),
        Index("idx_txn_user_category_date", "user_id", "category", "transaction_date"),
        Index("idx_txn_user_fingerprint", "user_id", "normalized_fingerprint"),
        Index("idx_txn_account_user", "account_id", "user_id"),
        Index("idx_txn_import_account_user", "import_id", "account_id", "user_id"),
        Index("uq_txn_account_provider_id", "account_id", "provider_transaction_id", unique=True),
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(enum_type(TransactionType, "txn_type"), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="Other", server_default=text("'Other'"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    description_cleaned: Mapped[str] = mapped_column(Text, nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(128))
    normalized_merchant: Mapped[str | None] = mapped_column(String(128))
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255))
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    normalized_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    source: Mapped[TransactionSource] = mapped_column(
        enum_type(TransactionSource, "txn_source"),
        default=TransactionSource.CSV_UPLOAD,
        server_default=text("'csv_upload'"),
        nullable=False,
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    account: Mapped[Account] = relationship(back_populates="transactions")
