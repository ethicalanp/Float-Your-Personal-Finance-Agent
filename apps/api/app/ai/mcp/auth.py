import uuid

from app.core.security import create_access_token, decode_access_token

SCOPE_FINANCE_READ = "finance:read"
SCOPE_PROTECT_READ = "protect:read"
SCOPE_BORROW_READ = "borrow:read"
SCOPE_DRAFTS_CREATE = "drafts:create"
SCOPE_KNOWLEDGE_READ = "knowledge:read"

ALL_SCOPES = [
    SCOPE_FINANCE_READ,
    SCOPE_PROTECT_READ,
    SCOPE_BORROW_READ,
    SCOPE_DRAFTS_CREATE,
    SCOPE_KNOWLEDGE_READ,
]

TOOL_SCOPE_MAP: dict[str, str] = {
    "get_cash_flow": SCOPE_FINANCE_READ,
    "check_scam_message": SCOPE_PROTECT_READ,
    "get_borrow_readiness": SCOPE_BORROW_READ,
    "draft_complaint": SCOPE_DRAFTS_CREATE,
    "get_verified_contacts": SCOPE_PROTECT_READ,
    "search_knowledge": SCOPE_KNOWLEDGE_READ,
}


def create_mcp_token(
    user_id: uuid.UUID | str,
    scopes: list[str] | None = None,
    expires_minutes: int = 60,
) -> str:
    """Create a scoped JWT token for MCP clients carrying authorized role scopes."""
    effective_scopes = scopes if scopes is not None else ALL_SCOPES
    return create_access_token(
        subject=str(user_id),
        claims={"scopes": effective_scopes},
        expires_minutes=expires_minutes,
    )


def decode_mcp_token(token: str) -> tuple[uuid.UUID, list[str]]:
    """Decode and validate an MCP bearer token returning (user_id, scopes)."""
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise ValueError("Token missing subject (sub)")
    scopes = payload.get("scopes", [])
    return uuid.UUID(user_id_str), list(scopes)
