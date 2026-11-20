import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import ConsentType, enum_type


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "normalized_email = lower(trim(email))",
            name="ck_users_normalized_email",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    consents: Mapped[list["Consent"]] = relationship(back_populates="user")


class Consent(Base):
    __tablename__ = "user_consents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        enum_type(ConsentType, "consent_type"), nullable=False
    )
    consent_version: Mapped[str] = mapped_column(
        String(32), default="v1.0", server_default=text("'v1.0'"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address_mask: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(back_populates="consents")

    __table_args__ = (
        Index(
            "idx_consent_user_type",
            "user_id",
            "consent_type",
        ),
        Index(
            "uq_user_consents_active",
            "user_id",
            "consent_type",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "idx_user_consents_history",
            "user_id",
            "consent_type",
            "consent_version",
            "granted_at",
        ),
    )
