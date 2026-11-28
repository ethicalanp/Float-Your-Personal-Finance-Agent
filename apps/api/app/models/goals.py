import uuid
from datetime import UTC, date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint("target_amount_paise > 0", name="ck_goals_target_positive"),
        CheckConstraint("saved_paise >= 0", name="ck_goals_saved_nonnegative"),
        CheckConstraint("priority >= 1", name="ck_goals_priority_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    saved_paise: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )


class EmergencyFundConfig(Base):
    __tablename__ = "emergency_fund_configs"
    __table_args__ = (
        CheckConstraint("target_months >= 0 AND target_months <= 36", name="ck_ef_target_months_range"),
        CheckConstraint("saved_paise >= 0", name="ck_ef_saved_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    target_months: Mapped[int] = mapped_column(Integer, default=6, server_default=text("6"), nullable=False)
    saved_paise: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )
