import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import ReadinessBand, enum_type


class BorrowAssessment(Base):
    __tablename__ = "borrow_assessments"
    __table_args__ = (
        Index("idx_borrow_user_created", "user_id", "created_at"),
        Index("idx_borrow_user_model_created", "user_id", "model_version", "created_at"),
        CheckConstraint(
            "default_probability >= 0 AND default_probability <= 1",
            name="ck_borrow_default_probability_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    default_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    readiness_band: Mapped[ReadinessBand] = mapped_column(
        enum_type(ReadinessBand, "readiness_band"), nullable=False
    )
    top_factors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'"), nullable=False
    )
    recommendations: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'"), nullable=False
    )
    input_features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
