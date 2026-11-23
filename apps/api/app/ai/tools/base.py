import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


def quantize_currency(value: Decimal | float | int | str) -> Decimal:
    """Format and round financial currency amounts to 2 decimal places using ROUND_HALF_UP.

    Guarantees:
    - Never uses raw float arithmetic for financial totals.
    - Deterministic rounding (ROUND_HALF_UP).
    """
    if isinstance(value, Decimal):
        dec = value
    else:
        dec = Decimal(str(value))
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_percent(value: Decimal | float | int | str) -> Decimal:
    """Format and round percentage values to 2 decimal places using ROUND_HALF_UP."""
    if isinstance(value, Decimal):
        dec = value
    else:
        dec = Decimal(str(value))
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_percentage_change(
    baseline: Decimal,
    current: Decimal,
) -> tuple[Decimal | None, str | None]:
    """Calculate percentage change between baseline and current value.

    Guarantees:
    - If baseline is 0.00, returns (None, warning_message), never infinity or division by zero.
    """
    zero = Decimal("0.00")
    if baseline == zero:
        return None, "Baseline value is zero; percentage change is undefined"

    pct = ((current - baseline) / abs(baseline)) * Decimal("100")
    return quantize_percent(pct), None


@dataclass(frozen=True)
class ToolContext:
    """Execution context provided to tools by the framework from authenticated request.

    HARD RULE: ToolContext is NEVER visible to or controllable by the LLM.
    """

    user_id: uuid.UUID
    request_id: str
    session: AsyncSession | Session
    locale: str = "en_IN"
    timezone: str = "Asia/Kolkata"


class Fact(BaseModel):
    """An atomic, grounded financial fact that an AI assistant may quote.

    Phase 6 verification will assert that every number in an answer matches a Fact.
    """

    id: str
    label: str
    value: str  # Always formatted string of Decimal or integer count
    unit: str  # "INR", "%", "count", "months", "days"
    period: str | None = None


class ToolResult(BaseModel):
    """Standardized output structure for all financial tools."""

    ok: bool
    tool: str
    data: dict[str, Any]
    facts: list[Fact] = Field(default_factory=list)
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period: str | None = None
    row_count: int = 0
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    data_quality: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Tool:
    """Specification of a typed, permissioned, read-only financial tool."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], Awaitable[ToolResult]]
    timeout: float = 5.0
    max_rows: int = 200
