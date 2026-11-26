import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import UnauthorizedException
from app.core.security import create_access_token
from app.models.enums import AuthAuditEventType
from app.models.user import UserSession
from app.services.auth_audit import log_auth_event
from app.services.phone_service import ensure_utc, mask_ip_address


def hash_token(raw_token: str) -> str:
    """SHA-256 hash of an opaque token for database storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_user_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    user_agent: str | None = None,
    ip_address: str | None = None,
    session_family_id: uuid.UUID | None = None,
) -> tuple[str, str, uuid.UUID]:
    """Create a user session, issue access + opaque refresh tokens, and return them."""
    settings = get_settings()
    session_id = uuid.uuid4()
    family_id = session_family_id or uuid.uuid4()
    raw_refresh_token = secrets.token_urlsafe(48)
    token_hash = hash_token(raw_refresh_token)

    now = datetime.now(UTC)
    expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    session = UserSession(
        id=session_id,
        user_id=user_id,
        session_family_id=family_id,
        refresh_token_hash=token_hash,
        is_revoked=False,
        expires_at=expires_at,
        created_at=now,
        last_active_at=now,
        user_agent=user_agent[:512] if user_agent else None,
        ip_address_mask=mask_ip_address(ip_address),
    )
    db.add(session)
    await db.flush()

    access_token = create_access_token(
        subject=str(user_id),
        claims={
            "sid": str(session_id),
            "auth_time": int(now.timestamp()),
        },
    )
    return access_token, raw_refresh_token, session_id


async def rotate_refresh_token(
    db: AsyncSession,
    raw_refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str, uuid.UUID]:
    """Rotate an opaque refresh token with automatic reuse detection."""
    settings = get_settings()
    token_hash = hash_token(raw_refresh_token)

    result = await db.execute(select(UserSession).where(UserSession.refresh_token_hash == token_hash))
    session = result.scalar_one_or_none()

    if session is None:
        raise UnauthorizedException("Invalid or expired refresh token.")

    # REUSE DETECTION: If this refresh token has already been revoked, the family is compromised!
    if session.is_revoked:
        await db.execute(
            update(UserSession)
            .where(UserSession.session_family_id == session.session_family_id)
            .values(is_revoked=True)
        )
        await log_auth_event(
            db,
            AuthAuditEventType.REFRESH_REUSE_DETECTED,
            user_id=session.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"family_id": str(session.session_family_id)},
        )
        await db.commit()
        raise UnauthorizedException(
            "Suspicious activity detected. All active sessions in this family have been revoked."
        )

    now = datetime.now(UTC)
    if ensure_utc(session.expires_at) <= now:
        session.is_revoked = True
        await db.commit()
        raise UnauthorizedException("Refresh token has expired.")

    # Mark the old session as revoked
    session.is_revoked = True

    # Issue a new session in the same family
    new_session_id = uuid.uuid4()
    new_refresh_token = secrets.token_urlsafe(48)
    new_token_hash = hash_token(new_refresh_token)
    new_expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    new_session = UserSession(
        id=new_session_id,
        user_id=session.user_id,
        session_family_id=session.session_family_id,
        refresh_token_hash=new_token_hash,
        is_revoked=False,
        expires_at=new_expires_at,
        created_at=now,
        last_active_at=now,
        user_agent=user_agent[:512] if user_agent else None,
        ip_address_mask=mask_ip_address(ip_address),
    )
    db.add(new_session)

    new_access_token = create_access_token(
        subject=str(session.user_id),
        claims={
            "sid": str(new_session_id),
            "auth_time": int(now.timestamp()),
        },
    )

    await log_auth_event(
        db,
        AuthAuditEventType.REFRESH_SUCCESS,
        user_id=session.user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return new_access_token, new_refresh_token, new_session_id


async def revoke_user_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> bool:
    """Revoke a specific active session."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is not None and not session.is_revoked:
        session.is_revoked = True
        await db.commit()
        return True
    return False


async def revoke_all_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """Revoke all active sessions belonging to the user."""
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.is_revoked.is_(False),
        )
        .values(is_revoked=True)
    )
    await db.commit()
    rowcount = getattr(result, "rowcount", 0)
    return int(rowcount or 0)
