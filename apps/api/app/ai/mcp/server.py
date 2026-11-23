import logging
import uuid
from typing import Any, Literal

from app.ai.mcp.auth import (
    SCOPE_BORROW_READ,
    SCOPE_DRAFTS_CREATE,
    SCOPE_FINANCE_READ,
    SCOPE_KNOWLEDGE_READ,
    SCOPE_PROTECT_READ,
    decode_mcp_token,
)
from app.ai.mcp.tools import (
    BorrowReadinessToolInput,
    CashFlowToolInput,
    CheckScamInput,
    DraftComplaintInput,
    GetVerifiedContactsInput,
    SearchKnowledgeInput,
    execute_borrow_readiness,
    execute_cash_flow,
    execute_check_scam_message,
    execute_draft_complaint,
    execute_get_verified_contacts,
    execute_search_knowledge,
)
from app.db.session import get_async_session_factory

logger = logging.getLogger("app.ai.mcp.server")

# Try importing FastMCP lazily
try:
    from fastmcp import Context, FastMCP
    from fastmcp.server.auth import AccessToken, require_scopes
    from fastmcp.server.dependencies import get_access_token

    FASTMCP_AVAILABLE = True
except ImportError:
    FASTMCP_AVAILABLE = False
    FastMCP = Any  # type: ignore[misc,assignment]
    Context = Any  # type: ignore[misc,assignment]
    require_scopes = None  # type: ignore[assignment]


class FloatJWTAuthProvider:
    """FastMCP AuthProvider verifying Float HS256 JWT bearer tokens and extracting scopes."""

    def __init__(self, required_scopes: list[str] | None = None) -> None:
        self.required_scopes = required_scopes or []

    async def verify_token(self, token: str) -> Any:
        try:
            user_id, scopes = decode_mcp_token(token)
            return AccessToken(
                token=token,
                client_id=str(user_id),
                subject=str(user_id),
                scopes=scopes,
                claims={"sub": str(user_id), "scopes": scopes},
            )
        except Exception as e:
            logger.warning("Token verification failed: %s", e)
            return None


def _resolve_user_id() -> uuid.UUID:
    """Resolve authenticated user UUID from FastMCP access token in context."""
    if not FASTMCP_AVAILABLE:
        return uuid.UUID("00000000-0000-0000-0000-000000000001")

    token = get_access_token()
    if token and token.subject:
        try:
            return uuid.UUID(str(token.subject))
        except ValueError:
            pass
    # If no token subject, fallback to dev zero UUID
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


def create_float_mcp_server(name: str = "Float Personal Finance Agent MCP") -> Any:
    """Factory creating and configuring the Float FastMCP server with 6 scoped tools."""
    if not FASTMCP_AVAILABLE:
        raise RuntimeError("fastmcp is not installed. Install with `pip install fastmcp` or `pip install .[mcp]`.")

    auth_provider = FloatJWTAuthProvider(required_scopes=[])
    server = FastMCP(
        name=name,
        instructions=(
            "Float MCP server providing read-only personal finance, fraud prevention, "
            "credit readiness, complaint drafting, and regulatory knowledge tools."
        ),
        auth=auth_provider,  # type: ignore[arg-type]
    )

    # 1. get_cash_flow (finance:read)
    @server.tool(name="get_cash_flow", auth=require_scopes(SCOPE_FINANCE_READ))
    async def get_cash_flow(
        start_date: str,
        end_date: str,
        bucket: Literal["daily", "weekly", "monthly"] = "monthly",
    ) -> dict[str, Any]:
        """Compute aggregated cash inflow, outflow, and net balance over time buckets."""
        from datetime import date

        user_id = _resolve_user_id()
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            inp = CashFlowToolInput(
                start_date=date.fromisoformat(start_date),
                end_date=date.fromisoformat(end_date),
                bucket=bucket,
            )
            return await execute_cash_flow(inp, user_id=user_id, session=session)

    # 2. check_scam_message (protect:read)
    @server.tool(name="check_scam_message", auth=require_scopes(SCOPE_PROTECT_READ))
    async def check_scam_message(
        message: str,
    ) -> dict[str, Any]:
        """Analyze suspicious messages, SMS, or WhatsApp texts using Protect scam detection rules."""
        inp = CheckScamInput(message=message)
        return await execute_check_scam_message(inp)

    # 3. get_borrow_readiness (borrow:read)
    @server.tool(name="get_borrow_readiness", auth=require_scopes(SCOPE_BORROW_READ))
    async def get_borrow_readiness(
        as_of_date: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve indicative borrow readiness evaluation. Returns unavailable state if insufficient data."""
        from datetime import date

        user_id = _resolve_user_id()
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            inp = BorrowReadinessToolInput(
                as_of_date=date.fromisoformat(as_of_date) if as_of_date else None,
            )
            return await execute_borrow_readiness(inp, user_id=user_id, session=session)

    # 4. draft_complaint (drafts:create)
    @server.tool(name="draft_complaint", auth=require_scopes(SCOPE_DRAFTS_CREATE))
    async def draft_complaint(
        bank_name: str,
        account_number_mask: str,
        transaction_reference: str,
        transaction_amount: float,
        incident_date: str | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a formal fraud grievance draft in pending_confirmation status. Never sent automatically."""
        user_id = _resolve_user_id()
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            inp = DraftComplaintInput(
                bank_name=bank_name,
                account_number_mask=account_number_mask,
                transaction_reference=transaction_reference,
                transaction_amount=transaction_amount,
                incident_date=incident_date,
                description=description,
            )
            return await execute_draft_complaint(inp, user_id=user_id, session=session)

    # 5. get_verified_contacts (protect:read)
    @server.tool(name="get_verified_contacts", auth=require_scopes(SCOPE_PROTECT_READ))
    async def get_verified_contacts(
        category: Literal["government", "public_bank", "private_bank", "telecom", "all"] = "all",
        search_query: str | None = None,
    ) -> dict[str, Any]:
        """Lookup official bank nodal contacts, cybercrime helpline 1930, and emergency block numbers."""
        inp = GetVerifiedContactsInput(category=category, search_query=search_query)
        return await execute_get_verified_contacts(inp)

    # 6. search_knowledge (knowledge:read)
    @server.tool(name="search_knowledge", auth=require_scopes(SCOPE_KNOWLEDGE_READ))
    async def search_knowledge(
        query: str,
        language: str = "en",
        top_k: int = 3,
    ) -> dict[str, Any]:
        """Search verified regulatory documentation with cited snippets. Strict query length cap."""
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            inp = SearchKnowledgeInput(query=query, language=language, top_k=top_k)
            return await execute_search_knowledge(inp, session=session)

    return server


# Top-level instance for FastMCP CLI and standard client runners
mcp: Any = create_float_mcp_server() if FASTMCP_AVAILABLE else None
