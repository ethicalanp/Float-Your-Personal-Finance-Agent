import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

DEFAULT_CATEGORY_MAPPINGS: dict[str, str] = {
    "Rent & Housing": "needs",
    "Utilities": "needs",
    "Groceries": "needs",
    "Healthcare": "needs",
    "Transport": "needs",
    "EMI": "needs",
    "Insurance": "needs",
    "Dining": "wants",
    "Entertainment": "wants",
    "Shopping": "wants",
    "Subscriptions": "wants",
    "Travel": "wants",
    "Savings": "savings",
    "SIP": "savings",
    "Investments": "savings",
    "Other": "wants",
}


class BudgetPlan(Base):
    """Versioned monthly INR budget plan (paise precision) with IST month boundaries."""

    __tablename__ = "budget_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "month", "version", name="uq_budget_plan_user_month_version"),
        Index("idx_budget_plan_user_month_current", "user_id", "month", "is_current"),
        CheckConstraint("monthly_income_paise > 0", name="ck_budget_plan_income_positive"),
        CheckConstraint("extra_income_paise >= 0", name="ck_budget_plan_extra_income_nonnegative"),
        CheckConstraint(
            "needs_pct >= 0 AND wants_pct >= 0 AND savings_pct >= 0",
            name="ck_budget_plan_pct_nonnegative",
        ),
        CheckConstraint(
            "needs_paise >= 0 AND wants_paise >= 0 AND savings_paise >= 0",
            name="ck_budget_plan_paise_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM in IST
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)

    monthly_income_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extra_income_paise: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"), nullable=False)
    income_mode: Mapped[str] = mapped_column(
        String(32), default="fixed", server_default=text("'fixed'"), nullable=False
    )  # fixed, irregular_avg, irregular_conservative
    irregular_months: Mapped[int] = mapped_column(Integer, default=3, server_default=text("3"), nullable=False)

    needs_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("50.00"), nullable=False)
    wants_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("30.00"), nullable=False)
    savings_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("20.00"), nullable=False)

    needs_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wants_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    savings_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)

    category_mappings: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=lambda: dict(DEFAULT_CATEGORY_MAPPINGS), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
