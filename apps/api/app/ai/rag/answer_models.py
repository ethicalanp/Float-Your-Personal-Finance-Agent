import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LLMAnswerOutput(BaseModel):
    """Structured output expected from the LLM Gateway."""

    status: Literal["answered", "insufficient_evidence", "refused"] = Field(
        description="Whether answered from evidence, evidence was insufficient, or request was refused."
    )
    answer: str = Field(
        description="The grounded answer in requested language, or explanation of why evidence is insufficient."
    )
    cited_aliases: list[str] = Field(
        default_factory=list,
        description="List of evidence aliases cited (e.g. ['E1', 'E2']). Must be empty for insufficient or refused.",
    )
    refusal_reason: str | None = Field(
        default=None,
        description="Reason if refused (e.g. policy violation, investment advice request).",
    )


class Citation(BaseModel):
    """Server-resolved citation mapping alias back to validated document metadata."""

    alias: str
    chunk_id: str
    document_title: str
    publisher: str
    heading: str | None = None
    source_url: str
    effective_date: datetime | str | None = None


class KnowledgeQuestionRequest(BaseModel):
    """API request payload for grounded regulatory Q&A."""

    question: str = Field(
        min_length=3,
        max_length=1000,
        description="The user's query about banking regulations, scams, or borrowing rules.",
    )
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Optional existing conversation ID for follow-up context."
    )
    language_hint: str | None = Field(
        default=None, description="Optional preferred response language ('en', 'ml', 'manglish')."
    )


class KnowledgeAnswerResponse(BaseModel):
    """API response contract for grounded knowledge answers."""

    status: Literal["answered", "insufficient_evidence", "refused"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    refusal_reason: str | None = None
    language: str
    degraded: bool = False
    degraded_reason: str | None = None
    disclaimer: str
    trace_id: str
    prompt_version: str
    model: str
    provider: str
    validation_failures: list[str] = Field(default_factory=list)
    soft_abstain: bool = False
    related_questions: list[str] = Field(default_factory=list)
