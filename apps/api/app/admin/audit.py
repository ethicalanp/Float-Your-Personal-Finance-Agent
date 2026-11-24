import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditActor
from app.models.protect import AuditTrail


async def record_admin_audit(
    session: AsyncSession,
    admin_id: str | uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    admin_username: str | None = None,
    user_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditTrail:
    """Record an administrative operation in the immutable AuditTrail table.

    Never stores raw user content or secret tokens.
    """
    safe_metadata = {
        "admin_id": str(admin_id) if admin_id else "unknown",
        "admin_username": admin_username or "admin",
        **(metadata or {}),
    }

    entry = AuditTrail(
        id=uuid.uuid4(),
        user_id=user_id,
        actor=AuditActor.SYSTEM,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=safe_metadata,
    )
    session.add(entry)
    await session.flush()
    return entry
