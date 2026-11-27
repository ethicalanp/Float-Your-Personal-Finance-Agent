import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from secrets import compare_digest
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.dependencies import get_orchestrator
from app.ai.agent.models import AssistantChatRequest, AssistantChatResponse
from app.ai.agent.orchestrator import AssistantOrchestrator
from app.ai.gateway.dependencies import get_llm_gateway
from app.ai.gateway.errors import AuthError, BudgetExceeded
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.resilience import CircuitState
from app.ai.observability.metrics import assistant_metrics
from app.ai.rag.answer import ConsentRequiredError, KnowledgeAnswerService
from app.ai.rag.answer_models import KnowledgeAnswerResponse, KnowledgeQuestionRequest
from app.ai.rag.dependencies import get_embedder, get_knowledge_service
from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.retrieval import RetrievalFailedError
from app.core.config import get_settings
from app.core.dependencies import get_current_active_user, get_db
from app.core.errors import AppException, ForbiddenException, NotFoundException
from app.core.security import decode_access_token
from app.models.conversations import Conversation, Message
from app.models.enums import AuditActor
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.protect import AuditTrail
from app.models.user import User

logger = logging.getLogger("app.api.v1.assistant")

router = APIRouter(prefix="/assistant", tags=["Assistant — AI Subsystem"])


class AssistantStatusResponse(BaseModel):
    status: Literal["available", "degraded", "unavailable"]
    provider: str
    model: str
    approved_for_real_data: bool
    circuit_state: str


class SubsystemHealth(BaseModel):
    status: Literal["ok", "degraded", "down"]
    latency_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AssistantLivenessResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str
    timestamp: float


class AssistantHealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: float
    database: SubsystemHealth
    embedder: SubsystemHealth
    gateway: SubsystemHealth


class AssistantReadinessResponse(BaseModel):
    ready: bool
    checks: dict[str, Any]
    details: str | None = None


class PurgeConversationsRequest(BaseModel):
    confirm: bool = Field(..., description="Must be set to True to confirm permanent deletion.")
    confirmation_phrase: str = Field(
        ...,
        description="Must match exactly 'DELETE_MY_CONVERSATIONS' to prevent accidental data loss.",
    )


class ConversationPurgeResponse(BaseModel):
    status: str
    purged_conversations: int
    purged_messages: int
    purged_audit_records: int


_PURGE_RATE_LIMIT_STORE: dict[str, float] = {}
PURGE_RATE_LIMIT_SECONDS = 60.0


async def verify_admin_or_internal_token(
    request: Request,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Verify access via X-Internal-Token header or authenticated admin user Bearer token.

    Access is strictly restricted to internal automation or an administrative user role.
    Regular authenticated users receive 403 Forbidden.
    Unauthenticated callers receive 401 Unauthorized.
    """
    settings = request.app.state.settings
    internal_token = settings.internal_metrics_token.get_secret_value() if settings.internal_metrics_token else None

    # 1. Internal token match
    if internal_token and x_internal_token and compare_digest(x_internal_token, internal_token):
        return

    # 2. Bearer token match
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if internal_token and compare_digest(token, internal_token):
            return
        try:
            payload = decode_access_token(token)
            if payload.get("sub"):
                role = payload.get("role", "user")
                if role == "admin":
                    return
                raise ForbiddenException("Admin role or internal token required for this endpoint")
        except ForbiddenException:
            raise
        except Exception:
            pass

    raise AppException(
        message="Authentication required for internal metrics. Provide valid X-Internal-Token or admin Bearer token.",
        code="UNAUTHORIZED",
        status_code=401,
    )


@router.get("/metrics", response_class=PlainTextResponse)
async def get_prometheus_metrics(_auth: None = Depends(verify_admin_or_internal_token)) -> Response:
    """Expose AI subsystem Prometheus-formatted metrics for Prometheus scraping.

    Access Control:
    - Strictly restricted to X-Internal-Token header or authenticated admin Bearer token.
    - Regular users are rejected with 403 Forbidden.

    Note on Multi-Worker Deployments:
    - This in-memory registry accumulates counters per process worker.
    - In a multi-worker deployment (e.g. Uvicorn with multiple workers or Gunicorn),
      metrics scraped from separate worker processes reflect local in-memory slices
      unless Prometheus multiprocess mode (PROMETHEUS_MULTIPROC_DIR) or a centralized
      Redis accumulator is configured.
    """
    content = assistant_metrics.format_prometheus_text()
    return PlainTextResponse(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/health", response_model=AssistantLivenessResponse)
async def get_assistant_health_liveness() -> AssistantLivenessResponse:
    """Unauthenticated liveness probe for load balancers.

    Returns minimal status without disclosing internal component topologies or configuration.
    Detailed health is moved to authenticated endpoint GET /api/v1/assistant/health/details.
    """
    return AssistantLivenessResponse(
        status="healthy",
        service="assistant",
        timestamp=time.time(),
    )


@router.get("/health/details", response_model=AssistantHealthResponse)
async def get_assistant_health_details(
    _auth: None = Depends(verify_admin_or_internal_token),
    session: AsyncSession = Depends(get_db),
    gateway: LLMGateway = Depends(get_llm_gateway),
    embedder: BaseEmbedder = Depends(get_embedder),
) -> AssistantHealthResponse:
    """Authenticated component health inspection verifying internal AI subsystem infrastructure.

    Inspects database round-trip latency, vector embedder dimension, and LLM circuit state.
    Requires internal token or admin role. Regular users receive 403 Forbidden.
    """
    # 1. Database check
    t0 = time.monotonic()
    db_status: Literal["ok", "degraded", "down"] = "ok"
    try:
        await session.execute(text("SELECT 1;"))
        db_lat = round((time.monotonic() - t0) * 1000, 2)
    except Exception:
        db_status = "down"
        db_lat = None

    # 2. Embedder check
    emb_status: Literal["ok", "degraded", "down"] = "ok"
    emb_details = {
        "model_name": embedder.model_name,
        "dimension": embedder.dimension,
    }

    # 3. LLM Gateway check
    circuit_state = gateway.circuit_breaker.state
    gw_status: Literal["ok", "degraded", "down"] = "ok"
    if circuit_state == CircuitState.OPEN:
        gw_status = "down"
    elif circuit_state == CircuitState.HALF_OPEN:
        gw_status = "degraded"

    gw_details = {
        "provider": gateway.config.provider,
        "model": gateway.config.model,
        "circuit_state": circuit_state.value,
        "approved_for_real_data": gateway.config.approved_for_real_data,
    }

    overall: Literal["healthy", "degraded", "unhealthy"] = "healthy"
    if db_status == "down" or gw_status == "down":
        overall = "unhealthy"
    elif gw_status == "degraded":
        overall = "degraded"

    return AssistantHealthResponse(
        status=overall,
        timestamp=time.time(),
        database=SubsystemHealth(status=db_status, latency_ms=db_lat),
        embedder=SubsystemHealth(status=emb_status, details=emb_details),
        gateway=SubsystemHealth(status=gw_status, details=gw_details),
    )


@router.get("/ready", response_model=AssistantReadinessResponse)
async def get_assistant_readiness(
    response: Response,
    session: AsyncSession = Depends(get_db),
    embedder: BaseEmbedder = Depends(get_embedder),
) -> AssistantReadinessResponse:
    """Readiness probe verifying DB, extensions, knowledge tables, published chunk count, and embedding dimensions."""
    checks: dict[str, Any] = {}
    is_ready = True
    failure_reasons: list[str] = []

    # 1. Database Connectivity & Dialect
    bind = session.bind
    dialect_name = bind.dialect.name if bind else "postgresql"

    # 2. Vector & pg_trgm Extensions (PostgreSQL only)
    if dialect_name == "postgresql":
        try:
            ext_res = await session.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');")
            )
            installed_exts = {row[0] for row in ext_res.all()}
            has_vector = "vector" in installed_exts
            has_trgm = "pg_trgm" in installed_exts
            checks["vector_extension"] = has_vector
            checks["pg_trgm_extension"] = has_trgm
            if not has_vector:
                is_ready = False
                failure_reasons.append("Missing PostgreSQL 'vector' extension")
            if not has_trgm:
                is_ready = False
                failure_reasons.append("Missing PostgreSQL 'pg_trgm' extension")
        except Exception as e:
            is_ready = False
            checks["extensions"] = f"CheckFailed({type(e).__name__})"
            failure_reasons.append(f"Failed to query pg_extension: {type(e).__name__}")
    else:
        # SQLite / mock environment
        checks["vector_extension"] = "sqlite_mock"
        checks["pg_trgm_extension"] = "sqlite_mock"

    # 3. Knowledge tables exist
    try:
        await session.execute(select(KnowledgeDocument.id).limit(1))
        await session.execute(select(KnowledgeChunk.id).limit(1))
        checks["knowledge_tables_exist"] = True
    except Exception as e:
        is_ready = False
        checks["knowledge_tables_exist"] = False
        failure_reasons.append(f"Knowledge tables missing or unmigrated: {type(e).__name__}")

    # 4. Published chunk count > 0
    try:
        stmt_count = (
            select(func.count(KnowledgeChunk.id))
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.status == "published")
        )
        count_res = await session.execute(stmt_count)
        published_count = count_res.scalar() or 0
        checks["published_chunk_count"] = published_count
        if published_count <= 0:
            is_ready = False
            failure_reasons.append(f"Published chunk count is {published_count} (must be > 0)")
    except Exception as e:
        is_ready = False
        checks["published_chunk_count"] = f"CountFailed({type(e).__name__})"
        failure_reasons.append(f"Failed to count published chunks: {type(e).__name__}")

    # 5. Embedding dimension matches column
    try:
        expected_dim = embedder.dimension
        model_dim = getattr(KnowledgeChunk.__table__.c.embedding.type, "dim", 768)
        checks["embedder_dimension"] = expected_dim
        checks["column_dimension"] = model_dim
        if expected_dim != model_dim:
            is_ready = False
            failure_reasons.append(f"Dimension mismatch: embedder={expected_dim} vs column={model_dim}")
    except Exception as e:
        is_ready = False
        checks["dimension_check"] = f"Failed({type(e).__name__})"
        failure_reasons.append(f"Failed embedding dimension verification: {type(e).__name__}")

    if not is_ready:
        response.status_code = 503

    return AssistantReadinessResponse(
        ready=is_ready,
        checks=checks,
        details="; ".join(failure_reasons) if failure_reasons else "All readiness checks passed",
    )


@router.delete("/conversations", response_model=ConversationPurgeResponse)
async def purge_conversations(
    payload: PurgeConversationsRequest,
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationPurgeResponse:
    """Permanently delete conversation history and assistant chat audit records for the caller.

    Hard-Deletes (Permanent SQL DELETE):
    - `messages`: all rows where user_id == calling user.
    - `conversations`: all rows where user_id == calling user.
    - `audit_trail`: all rows where user_id == calling user and action == 'assistant_chat'.

    Does NOT Delete:
    - User account credentials or profile records.
    - Core transaction records, accounts, or recurring commitments.
    - /knowledge turns that do not create conversation rows.

    Safety:
    - Requires payload confirmation_phrase == 'DELETE_MY_CONVERSATIONS'.
    - Strictly scoped to user_id = calling_user.id. User A cannot delete User B's records.

    Future Architecture Proposal (Audit Anonymization Option):
    - An option for future implementation is to anonymize rather than hard-delete audit_trail rows:
      setting user_id = NULL and scrubbing IP/user-agent headers, retaining aggregate model
      observability metrics (route, latency, and status) without retaining consumer linkage.
    """
    if not payload.confirm or payload.confirmation_phrase != "DELETE_MY_CONVERSATIONS":
        raise AppException(
            message=(
                "Confirmation required: payload must include confirm=True "
                "and confirmation_phrase='DELETE_MY_CONVERSATIONS'"
            ),
            code="CONFIRMATION_REQUIRED",
            status_code=400,
        )

    # Rate limiting: max 1 purge operation per user per 60 seconds
    now = time.time()
    last_call = _PURGE_RATE_LIMIT_STORE.get(str(user.id))
    if last_call and (now - last_call) < PURGE_RATE_LIMIT_SECONDS:
        remaining = int(PURGE_RATE_LIMIT_SECONDS - (now - last_call))
        raise AppException(
            message=f"Rate limit exceeded for conversation purge. Please wait {remaining} seconds before retrying.",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
        )
    _PURGE_RATE_LIMIT_STORE[str(user.id)] = now

    # Delete messages first (referential integrity)
    res_msg = await session.execute(delete(Message).where(Message.user_id == user.id))
    purged_messages = int(getattr(res_msg, "rowcount", 0) or 0)

    # Delete conversations
    res_conv = await session.execute(delete(Conversation).where(Conversation.user_id == user.id))
    purged_conversations = int(getattr(res_conv, "rowcount", 0) or 0)

    # Purge assistant chat audit records
    res_audit = await session.execute(
        delete(AuditTrail).where(AuditTrail.user_id == user.id, AuditTrail.action == "assistant_chat")
    )
    purged_audits = int(getattr(res_audit, "rowcount", 0) or 0)

    await session.commit()

    return ConversationPurgeResponse(
        status="purged",
        purged_conversations=purged_conversations,
        purged_messages=purged_messages,
        purged_audit_records=purged_audits,
    )


@router.get("/status", response_model=AssistantStatusResponse)
async def get_assistant_status(
    _user: User = Depends(get_current_active_user),
    gateway: LLMGateway = Depends(get_llm_gateway),
) -> AssistantStatusResponse:
    """Report LLM assistant readiness, provider configuration, and circuit health.

    Zero secrets or keys are ever disclosed. Requires authenticated user.
    """
    circuit_state = gateway.circuit_breaker.state

    if circuit_state == CircuitState.OPEN:
        status: Literal["available", "degraded", "unavailable"] = "unavailable"
    elif circuit_state == CircuitState.HALF_OPEN:
        status = "degraded"
    else:
        status = "available"

    # If real provider is configured, probe authentication state
    if gateway.config.provider.lower() != "fake":
        try:
            is_valid = await gateway.validate_auth()
            if not is_valid:
                status = "degraded"
        except AuthError:
            logger.warning(
                "Provider authentication failed (401/403). Check key/env var name/quotes/whitespace."
            )
            status = "degraded"
        except Exception as e:
            logger.warning("Provider check encountered warning: %s", type(e).__name__)

    return AssistantStatusResponse(
        status=status,
        provider=gateway.config.provider,
        model=gateway.config.model,
        approved_for_real_data=gateway.config.approved_for_real_data,
        circuit_state=circuit_state.value if status != "degraded" else "degraded",
    )


@router.post("/knowledge", response_model=KnowledgeAnswerResponse)
async def ask_knowledge(
    payload: KnowledgeQuestionRequest,
    user: User = Depends(get_current_active_user),
    service: KnowledgeAnswerService = Depends(get_knowledge_service),
) -> KnowledgeAnswerResponse:
    """Grounded regulatory and knowledge Q&A over official RBI, I4C, and NPCI guidance.

    Enforces active user consent, PII masking, deterministic post-generation validation,
    abstention gating, and safe extractive fallbacks.
    """
    try:
        return await service.answer(payload, user=user)
    except ConsentRequiredError as e:
        raise ForbiddenException(message=str(e)) from e
    except BudgetExceeded as e:
        raise AppException(
            message="Daily token budget exceeded. Please try again tomorrow.",
            code="BUDGET_EXCEEDED",
            status_code=429,
        ) from e
    except RetrievalFailedError as e:
        is_fraud = service._is_fraud_topic(payload.question)
        answer_text = "The knowledge retrieval service is temporarily unavailable."
        if is_fraud:
            answer_text += service._format_helpline_text()
        return KnowledgeAnswerResponse(
            status="insufficient_evidence",
            answer=answer_text,
            citations=[],
            confidence="low",
            refusal_reason=None,
            language=payload.language_hint or "en",
            degraded=True,
            degraded_reason=str(e),
            disclaimer=service.DISCLAIMER,
            trace_id=uuid.uuid4().hex,
            prompt_version="rag_answer_v1:degraded",
            model=service.gateway.config.model,
            provider=service.gateway.config.provider,
            validation_failures=[],
        )


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_assistant(
    payload: AssistantChatRequest,
    user: User = Depends(get_current_active_user),
    orchestrator: AssistantOrchestrator = Depends(get_orchestrator),
) -> AssistantChatResponse:
    """Multi-turn orchestrator endpoint coordinating routing, tools, RAG, and grounded composition.

    Enforces active user consent, PII masking, safety overrides for scam/fraud inquiries,
    strict numeric grounding, and extractive structured fallbacks.
    """
    try:
        response = await orchestrator.run(payload, user=user)
        if response.status == "refusal" and "consent" in response.answer.lower():
            raise ForbiddenException(message=response.answer)
        return response
    except BudgetExceeded as e:
        raise AppException(
            message="Daily token budget exceeded. Please try again tomorrow.",
            code="BUDGET_EXCEEDED",
            status_code=429,
        ) from e


class ConversationItemResponse(BaseModel):
    id: str
    title: str | None
    created_at: str
    last_message_at: str


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class MessageItemResponse(BaseModel):
    id: str
    role: str
    content: str
    trace_id: str | None
    created_at: str


class ChatFeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    trace_id: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=300)


@router.get("/conversations", response_model=list[ConversationItemResponse])
async def list_conversations(
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> list[ConversationItemResponse]:
    """List conversations belonging to the authenticated user."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.last_message_at.desc())
        .limit(50)
    )
    res = await session.execute(stmt)
    return [
        ConversationItemResponse(
            id=str(c.id),
            title=c.title,
            created_at=c.created_at.isoformat(),
            last_message_at=c.last_message_at.isoformat(),
        )
        for c in res.scalars().all()
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageItemResponse])
async def list_conversation_messages(
    conversation_id: str,
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> list[MessageItemResponse]:
    """List masked messages for a user-owned conversation."""
    try:
        cid = uuid.UUID(conversation_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Conversation not found") from err

    conv_res = await session.execute(
        select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id)
    )
    if conv_res.scalar_one_or_none() is None:
        raise NotFoundException("Conversation not found")

    msg_res = await session.execute(
        select(Message)
        .where(Message.conversation_id == cid, Message.user_id == user.id)
        .order_by(Message.created_at.asc())
    )
    return [
        MessageItemResponse(
            id=str(m.id),
            role=m.role.value,
            content=m.content_masked,
            trace_id=m.trace_id,
            created_at=m.created_at.isoformat(),
        )
        for m in msg_res.scalars().all()
    ]


@router.patch("/conversations/{conversation_id}", response_model=ConversationItemResponse)
async def rename_conversation(
    conversation_id: str,
    payload: RenameConversationRequest,
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationItemResponse:
    """Rename a user-owned conversation."""
    try:
        cid = uuid.UUID(conversation_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Conversation not found") from err

    res = await session.execute(
        select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id)
    )
    conv = res.scalar_one_or_none()
    if conv is None:
        raise NotFoundException("Conversation not found")

    conv.title = payload.title.strip()
    await session.commit()
    await session.refresh(conv)
    return ConversationItemResponse(
        id=str(conv.id),
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        last_message_at=conv.last_message_at.isoformat(),
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a single user-owned conversation and its messages."""
    try:
        cid = uuid.UUID(conversation_id)
    except (ValueError, TypeError) as err:
        raise NotFoundException("Conversation not found") from err

    res = await session.execute(
        select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id)
    )
    if res.scalar_one_or_none() is None:
        raise NotFoundException("Conversation not found")

    await session.execute(delete(Message).where(Message.conversation_id == cid, Message.user_id == user.id))
    await session.execute(delete(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id))
    await session.commit()


@router.post("/feedback", status_code=201)
async def submit_chat_feedback(
    payload: ChatFeedbackRequest,
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Record thumbs up/down feedback without logging raw text."""
    session.add(
        AuditTrail(
            user_id=user.id,
            actor=AuditActor.USER,
            action="assistant_feedback",
            resource_type="agent_trace",
            resource_id=payload.trace_id or "none",
            metadata_json={"rating": payload.rating, "has_reason": bool(payload.reason and payload.reason.strip())},
        )
    )
    await session.commit()
    return {"status": "recorded"}


@router.post("/chat/stream")
async def stream_chat_assistant(
    payload: AssistantChatRequest,
    user: User = Depends(get_current_active_user),
    orchestrator: AssistantOrchestrator = Depends(get_orchestrator),
) -> Response:
    """Optional SSE streaming endpoint behind PFA_ENABLE_CHAT_STREAMING."""
    if not get_settings().enable_chat_streaming:
        raise AppException(
            message="Streaming is disabled on this server.",
            code="STREAMING_DISABLED",
            status_code=501,
        )

    response = await orchestrator.run(payload, user=user)
    if response.status == "refusal" and "consent" in response.answer.lower():
        raise ForbiddenException(message=response.answer)

    async def event_generator() -> AsyncIterator[str]:
        words = response.answer.split(" ")
        for idx, word in enumerate(words):
            chunk = word if idx == 0 else f" {word}"
            yield f"event: delta\ndata: {json.dumps({'delta': chunk})}\n\n"
        yield f"event: done\ndata: {response.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ----------------------------------------------------------------------------
# DRAFT CONFIRMATION & EXPORT ENDPOINTS
# ----------------------------------------------------------------------------


class CreateComplaintDraftRequest(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=100, description="Name of the bank or institution")
    account_number_mask: str = Field(
        ..., min_length=4, max_length=20, description="Masked account or card (e.g. XXXX-1234)"
    )
    transaction_reference: str = Field(
        ..., min_length=3, max_length=100, description="Transaction ID or reference number"
    )
    transaction_amount: float = Field(..., gt=0, description="Disputed transaction amount in INR")
    incident_date: str | None = Field(default=None, description="Date of transaction (YYYY-MM-DD)")
    description: str = Field(default="", max_length=1000, description="Brief narrative of the dispute")


@router.post("/drafts")
async def create_assistant_draft(
    payload: CreateComplaintDraftRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new formal grievance complaint draft in pending_confirmation status."""
    from app.ai.agent.draft_service import create_complaint_draft

    return await create_complaint_draft(
        user_id=user.id,
        bank_name=payload.bank_name,
        account_number_mask=payload.account_number_mask,
        transaction_reference=payload.transaction_reference,
        transaction_amount=payload.transaction_amount,
        incident_date=payload.incident_date,
        description=payload.description,
        session=db,
    )


@router.post("/drafts/{draft_id}/confirm")
async def confirm_assistant_draft(
    draft_id: str,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Confirm a complaint draft, enabling plain-text export."""
    from app.ai.agent.draft_service import confirm_draft

    return await confirm_draft(draft_id=draft_id, user_id=user.id, session=db)


@router.post("/drafts/{draft_id}/discard")
async def discard_assistant_draft(
    draft_id: str,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Discard a complaint draft, preventing export."""
    from app.ai.agent.draft_service import discard_draft

    return await discard_draft(draft_id=draft_id, user_id=user.id, session=db)


@router.get("/drafts/{draft_id}/export", response_class=PlainTextResponse)
async def export_assistant_draft(
    draft_id: str,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Export confirmed complaint draft as plain text. Rejects unconfirmed drafts."""
    from app.ai.agent.draft_service import export_draft_text

    export_text = await export_draft_text(draft_id=draft_id, user_id=user.id, session=db)
    return PlainTextResponse(content=export_text, media_type="text/plain")


# ----------------------------------------------------------------------------
# TRACE METADATA RETRIEVAL ENDPOINT
# ----------------------------------------------------------------------------


@router.get("/traces/{trace_id}")
async def get_assistant_trace(
    trace_id: str,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve agent run trace metadata ensuring strict user isolation.

    Contains run id, step durations, tool argument summaries (never raw text/amounts),
    and validation outcomes.
    """
    from app.ai.agent.planner import get_agent_trace
    from app.core.errors import NotFoundException

    trace = await get_agent_trace(trace_id=trace_id, user_id=str(user.id), session=db)
    if not trace:
        raise NotFoundException(f"Trace {trace_id} not found")
    return trace
