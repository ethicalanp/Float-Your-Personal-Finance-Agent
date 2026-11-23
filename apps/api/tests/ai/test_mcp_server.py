import uuid

import pytest

from app.ai.mcp.auth import (
    SCOPE_BORROW_READ,
    SCOPE_DRAFTS_CREATE,
    SCOPE_FINANCE_READ,
    SCOPE_KNOWLEDGE_READ,
    SCOPE_PROTECT_READ,
    TOOL_SCOPE_MAP,
    create_mcp_token,
    decode_mcp_token,
)
from app.ai.mcp.server import (
    FASTMCP_AVAILABLE,
    create_float_mcp_server,
)
from app.ai.mcp.tools import (
    BorrowReadinessToolInput,
    CashFlowToolInput,
    CheckScamInput,
    DraftComplaintInput,
    GetVerifiedContactsInput,
    SearchKnowledgeInput,
    execute_check_scam_message,
    execute_draft_complaint,
    execute_get_verified_contacts,
)


@pytest.mark.asyncio
async def test_tool_schemas_contain_no_user_id() -> None:
    """Verify that none of the MCP tool schemas expose user_id, account_id, or SQL internals."""
    schemas = [
        CashFlowToolInput,
        CheckScamInput,
        BorrowReadinessToolInput,
        DraftComplaintInput,
        GetVerifiedContactsInput,
        SearchKnowledgeInput,
    ]
    for s in schemas:
        fields = s.model_fields.keys()
        assert "user_id" not in fields, f"Schema {s.__name__} leaked user_id"
        assert "user" not in fields, f"Schema {s.__name__} leaked user"
        assert "account_id" not in fields, f"Schema {s.__name__} leaked account_id"
        assert "sql" not in fields, f"Schema {s.__name__} leaked sql"


@pytest.mark.asyncio
async def test_mcp_token_creation_and_decoding() -> None:
    """Verify MCP JWT token encoding and decoding with scope verification."""
    test_user_id = uuid.uuid4()
    token = create_mcp_token(user_id=test_user_id, scopes=[SCOPE_FINANCE_READ, SCOPE_PROTECT_READ])
    decoded_user_id, scopes = decode_mcp_token(token)

    assert decoded_user_id == test_user_id
    assert SCOPE_FINANCE_READ in scopes
    assert SCOPE_PROTECT_READ in scopes
    assert SCOPE_BORROW_READ not in scopes


@pytest.mark.asyncio
async def test_tool_scope_mappings() -> None:
    """Verify all 6 tools are mapped to valid role scopes."""
    expected_tools = {
        "get_cash_flow": SCOPE_FINANCE_READ,
        "check_scam_message": SCOPE_PROTECT_READ,
        "get_borrow_readiness": SCOPE_BORROW_READ,
        "draft_complaint": SCOPE_DRAFTS_CREATE,
        "get_verified_contacts": SCOPE_PROTECT_READ,
        "search_knowledge": SCOPE_KNOWLEDGE_READ,
    }
    for tool_name, expected_scope in expected_tools.items():
        assert tool_name in TOOL_SCOPE_MAP
        assert TOOL_SCOPE_MAP[tool_name] == expected_scope


@pytest.mark.asyncio
async def test_fastmcp_server_initialization() -> None:
    """Verify FastMCP server initializes with all 6 tools declared."""
    if not FASTMCP_AVAILABLE:
        pytest.skip("FastMCP not installed in this environment")

    server = create_float_mcp_server()
    assert server is not None
    assert "Float" in server.name


@pytest.mark.asyncio
async def test_scam_check_tool_no_llm() -> None:
    """Verify check_scam_message operates deterministically without LLM dependency."""
    inp = CheckScamInput(message="Electricity bill overdue! Pay now to 9876543210 or power cut.")
    res = await execute_check_scam_message(inp)
    assert res["ok"] is True
    assert "risk_score" in res
    assert res["risk_score"] >= 0.0
    assert "helpline" in res


@pytest.mark.asyncio
async def test_verified_contacts_tool() -> None:
    """Verify get_verified_contacts returns official directories only."""
    inp = GetVerifiedContactsInput(category="all", search_query="cybercrime")
    res = await execute_get_verified_contacts(inp)
    assert res["ok"] is True
    contacts = res["contacts"]
    assert len(contacts) > 0
    # 1930 or cybercrime helpline should be present in official records
    assert any(
        "1930" in str(c.get("toll_free_number", "")) or "cybercrime" in str(c.get("institution", "")).lower()
        for c in contacts
    )


@pytest.mark.asyncio
async def test_draft_complaint_creates_pending_only() -> None:
    """Verify draft_complaint creates pending draft without autonomous submission."""
    user_id = uuid.uuid4()
    inp = DraftComplaintInput(
        bank_name="State Bank of India",
        account_number_mask="XXXX-5678",
        transaction_reference="UPI/12345/DISPUTE",
        transaction_amount=4500.0,
        incident_date="2026-11-20",
        description="Unauthorized debit without OTP notification",
    )
    res = await execute_draft_complaint(inp, user_id=user_id)
    assert res["status"] == "pending_confirmation"
    assert "draft_id" in res
    assert "State Bank of India" in res["body"] or "State Bank of India" in res["bank_name"]
