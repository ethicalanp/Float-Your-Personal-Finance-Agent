import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScamCheckLog(Base):
    __tablename__ = "scam_check_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    message_masked: Mapped[str] = mapped_column(Text, nullable=False)
    language_detected: Mapped[str] = mapped_column(String(32), default="en", nullable=False)  # en, ml, manglish
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(32), default="SAFE", nullable=False)  # SAFE, LOW, MEDIUM, HIGH, CRITICAL
    indicators_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON array of reasons
    is_scam: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_feedback_accurate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    user_feedback_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    incident_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    scam_type: Mapped[str] = mapped_column(String(64), default="phishing", nullable=False)  # upi_fraud, imposter, otp_theft, etc.
    amount_lost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    platform: Mapped[str] = mapped_column(String(64), default="SMS", nullable=False)  # SMS, WhatsApp, Phone Call, Email
    incident_summary_masked: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="reported", nullable=False)  # reported, in_progress, resolved
    steps_completed_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON checklist of actions taken
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ScamSample(Base):
    """Daily labeled dataset for Malayalam, Manglish, and English scam examples."""
    __tablename__ = "scam_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)  # en, ml, manglish
    is_scam: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scam_type: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="user_submission", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditTrail(Base):
    """Immutable audit log for security, protect actions, and financial data imports."""
    __tablename__ = "audit_trail"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
