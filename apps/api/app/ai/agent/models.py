import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.rag.answer_models import Citation


class RouteClass(str, Enum):
    PERSONAL_FINANCE = "personal_finance"
    KNOWLEDGE = "knowledge"
    PROTECT = "protect"
    CREDIT_READINESS = "credit_readiness"
    COMBINED = "combined"
    OUT_OF_SCOPE = "out_of_scope"
    UNCLEAR = "unclear"


class AgentState(str, Enum):
    RECEIVED = "RECEIVED"
    CONSENT_CHECK = "CONSENT_CHECK"
    MASK = "MASK"
    ROUTE = "ROUTE"
    PLAN = "PLAN"
    EXECUTE_TOOLS = "EXECUTE_TOOLS"
    RETRIEVE = "RETRIEVE"
    VALIDATE_EVIDENCE = "VALIDATE_EVIDENCE"
    COMPOSE = "COMPOSE"
    VALIDATE_ANSWER = "VALIDATE_ANSWER"
    RESPOND = "RESPOND"
    FALLBACK = "FALLBACK"
    REFUSE = "REFUSE"


class RouteResult(BaseModel):
    route: RouteClass
    confidence: Literal["high", "medium", "low"]
    reason_code: str
    clarifying_question: str | None = None


class ToolCallSpec(BaseModel):
    tool_name: str
    arguments: dict[str, Any]


class OrchestratorPlan(BaseModel):
    route: RouteClass
    tool_calls: list[ToolCallSpec] = Field(default_factory=list)
    needs_retrieval: bool = False
    retrieval_query: str | None = None
    refusal_reason: str | None = None
    clarifying_question: str | None = None


class AssistantChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="User's query")
    conversation_id: uuid.UUID | None = Field(default=None, description="Optional conversation UUID")


class AssistantChatResponse(BaseModel):
    status: Literal["success", "clarification_needed", "refusal", "degraded_fallback", "insufficient_evidence"]
    answer: str
    language: str
    citations: list[Citation] = Field(default_factory=list)
    facts_used: list[str] = Field(default_factory=list, description="IDs of tool facts used")
    route: RouteClass
    confidence: str
    degraded: bool = False
    disclaimer: str | None = None
    clarifying_question: str | None = None
    trace_id: str
    prompt_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
