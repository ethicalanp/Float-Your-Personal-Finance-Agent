import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenException, UnauthorizedException
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.enums import ConsentType
from app.models.user import Consent, User


async def get_current_active_user(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Retrieve the current user from the database, verifying existence and active status."""
    try:
        user_uuid = uuid.UUID(current_user.user_id)
    except (ValueError, TypeError) as err:
        raise UnauthorizedException("Invalid user ID in token") from err

    query = select(User).where(User.id == user_uuid)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("User not found")
    if not user.is_active:
        raise ForbiddenException("User account is inactive or disabled")

    return user


def require_consent(consent_type: ConsentType) -> Callable[..., Any]:
    """Dependency factory that checks whether the user has active, unrevoked consent."""

    async def _consent_checker(
        user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        query = select(Consent).where(
            Consent.user_id == user.id,
            Consent.consent_type == consent_type,
            Consent.revoked_at.is_(None),
        )
        result = await db.execute(query)
        consent = result.scalar_one_or_none()

        if not consent:
            raise ForbiddenException(
                f"Required privacy consent '{consent_type.value}' has not been granted or has been revoked."
            )
        return user

    return _consent_checker
