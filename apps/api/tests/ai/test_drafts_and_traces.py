import uuid

import pytest

from app.ai.agent.draft_service import (
    DraftStatus,
    confirm_draft,
    create_complaint_draft,
    discard_draft,
    export_draft_text,
    get_draft,
)
from app.ai.agent.planner import (
    AgentTrace,
    StepExecutionRecord,
    get_agent_trace,
    record_agent_trace,
)
from app.ai.security.masking import mask_pii
from app.core.errors import AppException, ForbiddenException
from app.models.conversations import Message
from app.models.enums import MessageRole


@pytest.mark.asyncio
async def test_draft_lifecycle_and_unconfirmed_export_blocked() -> None:
    """Verify complaint draft starts pending_confirmation, cannot be exported until confirmed."""
    user_id = uuid.uuid4()
    draft = await create_complaint_draft(
        user_id=user_id,
        bank_name="Axis Bank",
        account_number_mask="XXXX-7777",
        transaction_reference="REF/AXIS/98765",
        transaction_amount=12000.0,
        incident_date="2026-11-21",
        description="Debit card cloned and unauthorized ATM withdrawal",
    )
    draft_id = draft["draft_id"]
    assert draft["status"] == DraftStatus.PENDING

    # Attempting to export an unconfirmed draft must fail
    with pytest.raises(AppException) as exc_info:
        await export_draft_text(draft_id=draft_id, user_id=user_id)
    assert "cannot be exported" in str(exc_info.value)
    assert exc_info.value.status_code == 400

    # Confirm the draft
    conf = await confirm_draft(draft_id=draft_id, user_id=user_id)
    assert conf["status"] == DraftStatus.CONFIRMED

    # Export now succeeds
    export_content = await export_draft_text(draft_id=draft_id, user_id=user_id)
    assert "FORMAL DISPUTE NOTICE" in export_content
    assert "CONFIRMED BY USER" in export_content
    assert "Axis Bank" in export_content
    assert "REF/AXIS/98765" in export_content


@pytest.mark.asyncio
async def test_draft_discard_blocks_export() -> None:
    """Verify discarded draft cannot be confirmed or exported."""
    user_id = uuid.uuid4()
    draft = await create_complaint_draft(
        user_id=user_id,
        bank_name="ICICI Bank",
        account_number_mask="XXXX-1111",
        transaction_reference="REF/ICICI/54321",
        transaction_amount=3000.0,
    )
    draft_id = draft["draft_id"]

    # Discard draft
    disc = await discard_draft(draft_id=draft_id, user_id=user_id)
    assert disc["status"] == DraftStatus.DISCARDED

    # Discarded draft cannot be exported
    with pytest.raises(AppException):
        await export_draft_text(draft_id=draft_id, user_id=user_id)

    # Discarded draft cannot be confirmed
    with pytest.raises(AppException):
        await confirm_draft(draft_id=draft_id, user_id=user_id)


@pytest.mark.asyncio
async def test_cross_user_draft_isolation() -> None:
    """Verify user B cannot view, confirm, discard, or export user A's draft."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    draft = await create_complaint_draft(
        user_id=user_a,
        bank_name="Kotak Bank",
        account_number_mask="XXXX-4444",
        transaction_reference="REF/KOTAK/112233",
        transaction_amount=7500.0,
    )
    draft_id = draft["draft_id"]

    # User B cannot read draft
    with pytest.raises(ForbiddenException):
        await get_draft(draft_id=draft_id, user_id=user_b)

    # User B cannot confirm draft
    with pytest.raises(ForbiddenException):
        await confirm_draft(draft_id=draft_id, user_id=user_b)

    # User B cannot discard draft
    with pytest.raises(ForbiddenException):
        await discard_draft(draft_id=draft_id, user_id=user_b)

    # User B cannot export draft
    with pytest.raises(ForbiddenException):
        await export_draft_text(draft_id=draft_id, user_id=user_b)


@pytest.mark.asyncio
async def test_agent_trace_metadata_and_user_isolation() -> None:
    """Verify agent trace stores execution metadata without raw amounts, and isolates by user."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())

    trace = AgentTrace(
        trace_id=trace_id,
        run_id=str(uuid.uuid4()),
        user_id=user_a,
        created_at=1700000000.0,
        status="success",
        fallback_used=False,
        steps=[
            StepExecutionRecord(
                step_index=1,
                tool_name="get_spending_summary",
                arguments_summary={"tool": "get_spending_summary", "start_date": "2026-11-01"},
                duration_ms=45.2,
                status="success",
            )
        ],
        duration_ms=120.0,
        validation_results={"numeric_grounding": True},
    )
    record_agent_trace(trace)

    # Owning user can read metadata
    retrieved = await get_agent_trace(trace_id=trace_id, user_id=user_a)
    assert retrieved is not None
    assert retrieved["trace_id"] == trace_id
    assert retrieved["duration_ms"] == 120.0
    assert "raw_amount" not in str(retrieved)

    # Foreign user receives None (isolated)
    foreign = await get_agent_trace(trace_id=trace_id, user_id=user_b)
    assert foreign is None


def test_conversation_storage_only_masks_pii() -> None:
    """Verify conversation message content is masked before storage."""
    raw_user_input = "My PAN is ABCDE1234F and Aadhaar is 2345 6789 0123. Debit card 4111 2222 3333 4444."
    masked = mask_pii(raw_user_input)

    msg = Message(
        conversation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=MessageRole.USER,
        content_masked=masked,
        trace_id=str(uuid.uuid4()),
    )
    assert msg.content_masked is not None
    assert "ABCDE1234F" not in msg.content_masked
    assert "2345 6789 0123" not in msg.content_masked
    assert "4111 2222 3333 4444" not in msg.content_masked
    assert "XXXXX" in msg.content_masked or "XXXX-XXXX" in msg.content_masked
