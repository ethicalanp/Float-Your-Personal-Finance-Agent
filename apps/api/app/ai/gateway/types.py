from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]
DataClass = Literal["demo", "masked_real"]


class LLMMessage(BaseModel):
    role: Role
    content: str
    name: str | None = None


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LLMRequest(BaseModel):
    messages: list[LLMMessage]
    response_schema: type[BaseModel] | dict[str, Any] | None = None
    temperature: float = 0.0
    max_output_tokens: int = 1024
    prompt_version: str = "v1"
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str | None = None  # Strictly for token budgets, NEVER transmitted upstream
    data_class: DataClass = "masked_real"


class LLMResponse(BaseModel):
    text: str
    parsed: Any | None = None
    usage: TokenUsage
    model: str
    provider: str
    latency_ms: float
    retries: int = 0
    finish_reason: str = "stop"
