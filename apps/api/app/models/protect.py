import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import AuditActor, CaseStatus, LanguageCode, RiskTier, enum_type


class ScamCheckLog(Base):
    __tablename__ = "scam_check_logs"
    __table_args__ = (
        Index("idx_scam_check_user_created", "user_id", "created_at"),
        Index("uq_scam_logs_id_user", "id", "user_id", unique=True),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_scam_risk_score_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    message_masked: Mapped[str] = mapped_column(Text, nullable=False)
    language_detected: Mapped[LanguageCode] = mapped_column(
        enum_type(LanguageCode, "language_code"),
        default=LanguageCode.EN,
        server_default=sql_text("'en'"),
        nullable=False,
    )
    risk_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), server_default=sql_text("0"), nullable=False
    )
    risk_tier: Mapped[RiskTier] = mapped_column(
        enum_type(RiskTier, "risk_tier"),
        default=RiskTier.SAFE,
        server_default=sql_text("'SAFE'"),
        nullable=False,
    )
    indicators: Mapped[dict[str, Any] | list[Any]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb"), nullable=False
    )
    model_version: Mapped[str | None] = mapped_column(String(64))
    is_scam: Mapped[bool] = mapped_column(default=False, server_default=sql_text("false"), nullable=False)
    user_feedback_accurate: Mapped[bool | None] = mapped_column()
    user_feedback_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"
    __table_args__ = (
        ForeignKeyConstraint(["scam_check_id", "user_id"], ["scam_check_logs.id", "scam_check_logs.user_id"]),
        Index("idx_recovery_user_status", "user_id", "status"),
        Index("idx_recovery_user_created", "user_id", "created_at"),
        Index("idx_recovery_scam_check_user", "scam_check_id", "user_id"),
        CheckConstraint("amount_lost >= 0", name="ck_recovery_amount_lost_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    scam_check_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    incident_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    scam_type: Mapped[str] = mapped_column(String(64), default="phishing", server_default=sql_text("'phishing'"), nullable=False)
    amount_lost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), server_default=sql_text("0"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(64), default="SMS", server_default=sql_text("'SMS'"), nullable=False)
    incident_summary_masked: Mapped[str] = mapped_column(Text, nullable=False)
    incident_details_encrypted: Mapped[bytes | None] = mapped_column()
    encryption_key_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[CaseStatus] = mapped_column(
        enum_type(CaseStatus, "case_status"),
        default=CaseStatus.REPORTED,
        server_default=sql_text("'reported'"),
        nullable=False,
    )
    steps_completed: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class VerifiedContact(Base):
    __tablename__ = "verified_contacts"
    __table_args__ = (
        Index("idx_verified_contact_lookup", "institution", "contact_type", "country_code"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_verified_contacts_valid_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    institution: Mapped[str] = mapped_column(String(128), nullable=False)
    contact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), default="IN", server_default=sql_text("'IN'"), nullable=False)
    toll_free_number: Mapped[str | None] = mapped_column(String(64))
    fraud_reporting_email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    sms_block_code: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, server_default=sql_text("CURRENT_DATE"), nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)


class ScamSample(Base):
    __tablename__ = "scam_samples"
    __table_args__ = (Index("idx_scam_samples_language_scam", "language", "is_scam"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    language: Mapped[LanguageCode] = mapped_column(enum_type(LanguageCode, "language_code"), nullable=False)
    is_scam: Mapped[bool] = mapped_column(default=True, server_default=sql_text("true"), nullable=False)
    scam_type: Mapped[str] = mapped_column(String(64), default="unknown", server_default=sql_text("'unknown'"), nullable=False)
    source: Mapped[str] = mapped_column(
        String(64), default="user_submission", server_default=sql_text("'user_submission'"), nullable=False
    )
    labeled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditTrail(Base):
    __tablename__ = "audit_trail"
    __table_args__ = (
        Index("idx_audit_user_created", "user_id", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    actor: Mapped[AuditActor] = mapped_column(
        enum_type(AuditActor, "audit_actor"),
        default=AuditActor.USER,
        server_default=sql_text("'user'"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=sql_text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
