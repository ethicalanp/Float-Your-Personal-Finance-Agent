import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuthAuditEventType
from app.models.user import AuthAuditLog
from app.services.phone_service import hash_identifier, mask_ip_address

logger = logging.getLogger(__name__)


async def log_auth_event(
    db: AsyncSession,
    event_type: AuthAuditEventType,
    user_id: uuid.UUID | None = None,
    identifier: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an authentication audit event with hashed identifiers and masked IP."""
    ident_hash = hash_identifier(identifier) if identifier else None
    masked_ip = mask_ip_address(ip_address)
    meta_json = json.dumps(metadata) if metadata else None

    audit_entry = AuthAuditLog(
        event_type=event_type,
        user_id=user_id,
        identifier_hash=ident_hash,
        ip_address_mask=masked_ip,
        user_agent=user_agent[:512] if user_agent else None,
        metadata_json=meta_json[:1024] if meta_json else None,
    )
    db.add(audit_entry)
