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
    """Load the authenticated user and reject missing or inactive accounts."""
    try:
        user_uuid = uuid.UUID(current_user.user_id)
    except (ValueError, TypeError) as err:
        raise UnauthorizedException("Invalid user ID in token") from err

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedException("User not found")
    if not user.is_active:
        raise ForbiddenException("User account is inactive or disabled")
    return user


def require_consent(consent_type: ConsentType) -> Callable[..., Any]:
    """Require an active consent record for the requested operation."""

    async def _consent_checker(
        user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        result = await db.execute(
            select(Consent).where(
                Consent.user_id == user.id,
                Consent.consent_type == consent_type,
                Consent.revoked_at.is_(None),
            )
        )
        if result.scalar_one_or_none() is None:
            raise ForbiddenException(
                f"Required privacy consent '{consent_type.value}' has not been granted or has been revoked."
            )
        return user

    return _consent_checker


def require_recent_auth(max_age_seconds: int = 600) -> Callable[..., Any]:
    """Require recent authentication (<= max_age_seconds) for sensitive operations, else raise 403 reauth_required."""

    async def _recent_auth_checker(
        current_user: CurrentUser = Depends(get_current_user),
        user: User = Depends(get_current_active_user),
    ) -> User:
        import time

        now = int(time.time())
        auth_time = current_user.auth_time
        if auth_time is None or (now - auth_time) > max_age_seconds:
            raise ForbiddenException(
                message="Recent authentication is required for this action. Please re-authenticate.",
                code="reauth_required",
            )
        return user

    return _recent_auth_checker
