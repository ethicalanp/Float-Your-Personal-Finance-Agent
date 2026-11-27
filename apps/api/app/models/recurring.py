import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class RecurringCommitment(Base):
    __tablename__ = "recurring_commitments"
    __table_args__ = (Index("idx_recurring_commitments_user", "user_id", "is_active"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="Subscriptions", nullable=False)
    amount_type: Mapped[str] = mapped_column(String(32), default="fixed", nullable=False)  # fixed, variable_band
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    min_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    frequency: Mapped[str] = mapped_column(String(32), default="monthly", nullable=False)
    due_rule_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(128), nullable=True)
    merchant_keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), default="declared", nullable=False)  # declared, suggested_confirmed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    occurrences: Mapped[list["RecurringOccurrence"]] = relationship(
        "RecurringOccurrence", back_populates="commitment", cascade="all, delete-orphan"
    )


class RecurringOccurrence(Base):
    __tablename__ = "recurring_occurrences"
    __table_args__ = (
        Index("idx_recurring_occurrences_user_due", "user_id", "due_date", "status"),
        UniqueConstraint("commitment_id", "due_date", name="uq_commitment_occurrence_due"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    commitment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recurring_commitments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="upcoming", nullable=False
    )  # upcoming, paid, missed, overdue
    matched_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    match_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mismatch_flag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mismatch_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    commitment: Mapped["RecurringCommitment"] = relationship("RecurringCommitment", back_populates="occurrences")
    notifications: Mapped[list["RecurringNotification"]] = relationship(
        "RecurringNotification", back_populates="occurrence", cascade="all, delete-orphan"
    )


class RecurringNotification(Base):
    __tablename__ = "recurring_notifications"
    __table_args__ = (
        UniqueConstraint(
            "occurrence_id", "notification_type", "channel", name="uq_notification_occurrence_type_channel"
        ),
        Index("idx_notifications_user_sent", "user_id", "sent_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recurring_occurrences.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # due_in_3_days, due_tomorrow, low_balance_warning, missed_payment, candidate_suggestion
    channel: Mapped[str] = mapped_column(String(32), default="in_app", nullable=False)  # in_app, email
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message_masked: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    @property
    def message(self) -> str:
        return self.message_masked

    @message.setter
    def message(self, value: str) -> None:
        self.message_masked = value

    occurrence: Mapped["RecurringOccurrence"] = relationship("RecurringOccurrence", back_populates="notifications")
