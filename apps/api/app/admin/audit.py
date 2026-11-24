import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditActor
from app.models.protect import AuditTrail


async def record_admin_audit(
    session: AsyncSession,
    admin_username: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditTrail:
    """Record an administrative operation in the immutable AuditTrail table.

    Never stores raw user content or secret tokens.
    """
    safe_metadata = {
        "admin_username": admin_username,
        **(metadata or {}),
    }

    entry = AuditTrail(
        id=uuid.uuid4(),
        user_id=None,
        actor=AuditActor.SYSTEM,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=safe_metadata,
    )
    session.add(entry)
    await session.flush()
    return entry
