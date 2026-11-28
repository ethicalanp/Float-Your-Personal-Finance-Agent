import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.dependencies import get_current_active_user, get_db, require_recent_auth
from app.core.errors import (
    ConflictException,
    NotFoundException,
    ServiceUnavailableException,
    UnauthorizedException,
    ValidationException,
)
from app.core.security import (
    CurrentUser,
    decode_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.enums import (
    AuthAuditEventType,
    AuthProvider,
    AuthTokenType,
    ConsentType,
)
from app.models.user import AuthToken, Consent, User, UserIdentity, UserSession
from app.services.auth_audit import log_auth_event
from app.services.auth_lockout import lockout_tracker
from app.services.google_auth import verify_google_id_token
from app.services.phone_service import (
    ensure_utc,
    generate_otp,
    hash_identifier,
    hash_otp,
    mask_ip_address,
    normalize_phone_number,
    verify_otp_hash,
)
from app.services.session_service import (
    create_user_session,
    hash_token,
    revoke_all_user_sessions,
    rotate_refresh_token,
)
from app.services.sms_provider import Msg91SmsProvider, get_sms_provider

router = APIRouter(prefix="/auth", tags=["Authentication & Consent"])


# ============================================================================
# Schemas
# ============================================================================


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    terms_accepted: bool = False
    privacy_accepted: bool = False
    ai_data_processing_consent: bool = False
    consent_version: str = "v1.0"
    age_confirmed: bool | None = None
    age_confirmation_version: str = "v1.0"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class PhoneOtpRequest(BaseModel):
    phone_number: str


class PhoneOtpVerifyRequest(BaseModel):
    phone_number: str
    otp: str = Field(..., min_length=6, max_length=6)
    full_name: str | None = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class EmailVerifyRequest(BaseModel):
    email: EmailStr | None = None


class SetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8)


class ReauthRequest(BaseModel):
    method: str = Field(..., description="password | google | phone")
    password: str | None = None
    id_token: str | None = None
    phone_number: str | None = None
    otp: str | None = None


class PhoneLinkRequest(BaseModel):
    phone_number: str
    otp: str | None = Field(None, min_length=6, max_length=6)


class EmailVerifyConfirmRequest(BaseModel):
    token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str
    email: str | None = None
    full_name: str
    consent_given: bool


class ConsentUpdateRequest(BaseModel):
    terms_accepted: bool
    privacy_accepted: bool = False
    ai_data_processing_consent: bool
    consent_version: str = "v1.0"


class UserProfileResponse(BaseModel):
    user_id: str
    email: str | None = None
    full_name: str
    phone_number: str | None = None
    consent: dict[str, Any]


class MessageResponse(BaseModel):
    message: str
    cooldown_seconds: int | None = None


class UserSessionItem(BaseModel):
    id: str
    created_at: str
    last_active_at: str
    user_agent: str | None = None
    ip_address_mask: str | None = None
    is_current: bool = False


class AuthMethodItem(BaseModel):
    id: str
    provider: str
    identifier: str | None = None
    created_at: str


class AuthMethodsResponse(BaseModel):
    has_password: bool
    methods: list[AuthMethodItem]


class AuthCapabilitiesResponse(BaseModel):
    google: bool
    phone: bool
    email: bool = True
    google_client_id: str | None = None


# ============================================================================
# Helpers
# ============================================================================


def is_phone_auth_enabled(settings: Settings) -> bool:
    """Phone authentication is usable only if MSG91 is configured or ENV=local with fake."""
    env_str = os.environ.get("ENV", "").lower()
    is_local = env_str in ("local", "loc")
    if settings.sms_provider == "msg91":
        provider = get_sms_provider(settings)
        return isinstance(provider, Msg91SmsProvider) and provider.is_configured()
    if settings.sms_provider == "fake" and is_local:
        return True
    return False


def _get_request_meta(request: Request) -> tuple[str | None, str | None]:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return client_ip, user_agent


async def _check_user_consent_given(db: AsyncSession, user_id: uuid.UUID) -> bool:
    consent_result = await db.execute(
        select(Consent).where(
            Consent.user_id == user_id,
            Consent.revoked_at.is_(None),
        )
    )
    active = {c.consent_type for c in consent_result.scalars().all()}
    return ConsentType.TERMS in active and ConsentType.AI_DATA_PROCESSING in active


# ============================================================================
# Capabilities
# ============================================================================


@router.get("/capabilities", response_model=AuthCapabilitiesResponse)
async def get_auth_capabilities(
    settings: Settings = Depends(get_settings),
) -> AuthCapabilitiesResponse:
    """Public endpoint advertising available authentication capabilities."""
    if "PFA_GOOGLE_CLIENT_ID" in os.environ:
        google_id = os.environ["PFA_GOOGLE_CLIENT_ID"].strip()
    else:
        google_id = settings.google_client_id.strip() if settings.google_client_id else ""
    google_enabled = bool(google_id)
    phone_enabled = is_phone_auth_enabled(settings)
    return AuthCapabilitiesResponse(
        google=google_enabled,
        phone=phone_enabled,
        email=True,
        google_client_id=google_id if google_enabled else None,
    )


# ============================================================================
# Registration & Password Login
# ============================================================================


@router.post("/register", response_model=AuthTokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    """Register a new user, capture consent separately, and issue access & refresh tokens."""
    client_ip, user_agent = _get_request_meta(request)
    normalized_email = str(req.email).lower().strip()

    if req.age_confirmed is False:
        raise ValidationException("You must confirm that you are 18 years or older to register.")

    result = await db.execute(select(User).where(User.normalized_email == normalized_email))
    if result.scalar_one_or_none() is not None:
        raise ConflictException("A user with this email address already exists.")

    user = User(
        email=str(req.email),
        normalized_email=normalized_email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Link password identity
    identity = UserIdentity(
        user_id=user.id,
        provider=AuthProvider.PASSWORD,
        provider_user_id=normalized_email,
        email=str(req.email),
        last_sign_in_at=datetime.now(UTC),
    )
    db.add(identity)

    now = datetime.now(UTC)
    masked_ip = mask_ip_address(client_ip)
    if req.terms_accepted:
        db.add(
            Consent(
                user_id=user.id,
                consent_type=ConsentType.TERMS,
                consent_version=req.consent_version,
                granted_at=now,
                ip_address_mask=masked_ip,
            )
        )
    if req.privacy_accepted:
        db.add(
            Consent(
                user_id=user.id,
                consent_type=ConsentType.PRIVACY,
                consent_version=req.consent_version,
                granted_at=now,
                ip_address_mask=masked_ip,
            )
        )
    if req.ai_data_processing_consent:
        db.add(
            Consent(
                user_id=user.id,
                consent_type=ConsentType.AI_DATA_PROCESSING,
                consent_version=req.consent_version,
                granted_at=now,
                ip_address_mask=masked_ip,
            )
        )
    if req.age_confirmed is True:
        db.add(
            Consent(
                user_id=user.id,
                consent_type=ConsentType.AGE_18_PLUS,
                consent_version=req.age_confirmation_version,
                granted_at=now,
                ip_address_mask=masked_ip,
            )
        )

    access_token, refresh_token, _ = await create_user_session(
        db=db,
        user_id=user.id,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.REGISTER,
        user_id=user.id,
        identifier=normalized_email,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"method": "password"},
    )

    await db.commit()
    await db.refresh(user)

    consent_given = req.terms_accepted and req.ai_data_processing_consent
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=consent_given,
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    """Authenticate with email and password, returning access and refresh tokens."""
    client_ip, user_agent = _get_request_meta(request)
    normalized_email = str(req.email).lower().strip()

    is_locked, lock_scope = lockout_tracker.is_login_locked(normalized_email, client_ip)
    if is_locked:
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.LOGIN_FAILURE,
            identifier=normalized_email,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"reason": "locked_out", "scope": lock_scope},
        )
        await db.commit()
        raise UnauthorizedException("Invalid email or password.")

    result = await db.execute(select(User).where(User.normalized_email == normalized_email))
    user = result.scalar_one_or_none()

    if user is None or not user.hashed_password or not verify_password(req.password, user.hashed_password):
        delay = lockout_tracker.record_login_failure(normalized_email, client_ip)
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.LOGIN_FAILURE,
            identifier=normalized_email,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"reason": "bad_credentials", "lockout_delay_s": delay},
        )
        await db.commit()
        raise UnauthorizedException("Invalid email or password.")

    if not user.is_active:
        raise UnauthorizedException("User account is inactive.")

    lockout_tracker.clear_login_account(normalized_email)

    access_token, refresh_token, _ = await create_user_session(
        db=db,
        user_id=user.id,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    # Update identity last sign in
    ident_res = await db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == user.id,
            UserIdentity.provider == AuthProvider.PASSWORD,
        )
    )
    ident = ident_res.scalar_one_or_none()
    if ident is not None:
        ident.last_sign_in_at = datetime.now(UTC)

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.LOGIN_SUCCESS,
        user_id=user.id,
        identifier=normalized_email,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"method": "password"},
    )
    await db.commit()

    consent_given = await _check_user_consent_given(db, user.id)
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=consent_given,
    )


# ============================================================================
# Google Sign-In & Linking
# ============================================================================


@router.post("/google", response_model=AuthTokenResponse)
async def google_auth(
    req: GoogleAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    """Authenticate or register via Google ID token. Strictly verifies verified email."""
    client_ip, user_agent = _get_request_meta(request)
    payload = verify_google_id_token(req.id_token)

    sub = str(payload["sub"])
    email = str(payload["email"]).lower().strip()
    name = str(payload.get("name") or "Google User")

    # Check if Google identity already linked
    ident_res = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == AuthProvider.GOOGLE,
            UserIdentity.provider_user_id == sub,
        )
    )
    identity = ident_res.scalar_one_or_none()

    if identity is not None:
        user_res = await db.execute(select(User).where(User.id == identity.user_id))
        user = user_res.scalar_one_or_none()
        if user is None or not user.is_active:
            raise UnauthorizedException("User account is inactive or not found.")
        identity.last_sign_in_at = datetime.now(UTC)
    else:
        # Check if user with matching verified email exists
        user_res = await db.execute(select(User).where(User.normalized_email == email))
        user = user_res.scalar_one_or_none()

        if user is not None:
            # Link Google identity to existing verified email user
            identity = UserIdentity(
                user_id=user.id,
                provider=AuthProvider.GOOGLE,
                provider_user_id=sub,
                email=email,
                last_sign_in_at=datetime.now(UTC),
            )
            db.add(identity)
            await log_auth_event(
                db=db,
                event_type=AuthAuditEventType.IDENTITY_LINKED,
                user_id=user.id,
                identifier=email,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"provider": "google"},
            )
        else:
            # Create brand new user
            user = User(
                email=email,
                normalized_email=email,
                hashed_password=None,
                full_name=name,
                is_active=True,
            )
            db.add(user)
            await db.flush()

            identity = UserIdentity(
                user_id=user.id,
                provider=AuthProvider.GOOGLE,
                provider_user_id=sub,
                email=email,
                last_sign_in_at=datetime.now(UTC),
            )
            db.add(identity)
            await log_auth_event(
                db=db,
                event_type=AuthAuditEventType.REGISTER,
                user_id=user.id,
                identifier=email,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"method": "google"},
            )

    access_token, refresh_token, _ = await create_user_session(
        db=db,
        user_id=user.id,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.LOGIN_SUCCESS,
        user_id=user.id,
        identifier=email,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"method": "google"},
    )
    await db.commit()

    consent_given = await _check_user_consent_given(db, user.id)
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=consent_given,
    )


# ============================================================================
# Phone OTP Authentication
# ============================================================================


@router.post("/phone/request-otp", response_model=MessageResponse)
async def request_phone_otp(
    req: PhoneOtpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Request a 6-digit OTP sent via SMS with anti-pumping protection and rate limits."""
    if not is_phone_auth_enabled(settings):
        raise ServiceUnavailableException(
            "Phone authentication is currently unavailable.",
            code="phone_login_disabled",
        )

    client_ip, user_agent = _get_request_meta(request)

    normalized_phone = normalize_phone_number(
        req.phone_number,
        allowlist=settings.sms_country_allowlist,
    )
    ident_hash = hash_identifier(normalized_phone)
    now = datetime.now(UTC)

    generic_resp = MessageResponse(
        message="If the phone number is valid, an OTP has been sent.",
        cooldown_seconds=settings.otp_cooldown_seconds,
    )

    # 1. Global daily cap check
    one_day_ago = now - timedelta(days=1)
    daily_count_res = await db.execute(
        select(func.count(AuthToken.id)).where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.created_at >= one_day_ago,
        )
    )
    daily_count = daily_count_res.scalar() or 0
    effective_cap = min(settings.sms_daily_cap, settings.otp_daily_global_cap)
    if daily_count >= effective_cap:
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.OTP_REQUEST,
            identifier=normalized_phone,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"reason": "daily_cap_exceeded"},
        )
        await db.commit()
        return generic_resp

    # 2. Per-phone rate limit check (past hour)
    one_hour_ago = now - timedelta(hours=1)
    phone_count_res = await db.execute(
        select(func.count(AuthToken.id)).where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.identifier_hash == ident_hash,
            AuthToken.created_at >= one_hour_ago,
        )
    )
    phone_count = phone_count_res.scalar() or 0
    if phone_count >= settings.otp_rate_limit_per_phone_hour:
        return generic_resp

    # 3. Resend cooldown check (e.g. 60 seconds)
    cooldown_cutoff = now - timedelta(seconds=settings.otp_cooldown_seconds)
    recent_token_res = await db.execute(
        select(AuthToken)
        .where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.identifier_hash == ident_hash,
            AuthToken.created_at >= cooldown_cutoff,
        )
        .order_by(AuthToken.created_at.desc())
    )
    if recent_token_res.scalar_one_or_none() is not None:
        return generic_resp

    # Invalidate previous unused OTP tokens for this phone
    existing_tokens_res = await db.execute(
        select(AuthToken).where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.identifier_hash == ident_hash,
            AuthToken.is_used.is_(False),
        )
    )
    for tok in existing_tokens_res.scalars().all():
        tok.is_used = True

    # Generate and store HMAC OTP
    otp = generate_otp(6)
    token_hmac = hash_otp(otp, settings.jwt_secret_key)
    auth_token = AuthToken(
        identifier_hash=ident_hash,
        token_hash=token_hmac,
        token_type=AuthTokenType.OTP,
        created_at=now,
        expires_at=now + timedelta(seconds=settings.otp_expiry_seconds),
        attempts_count=0,
        max_attempts=settings.otp_max_attempts,
        is_used=False,
    )
    db.add(auth_token)

    sms_provider = get_sms_provider(settings)
    send_ok = await sms_provider.send_otp(normalized_phone, otp)

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.OTP_REQUEST,
        identifier=normalized_phone,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"provider": settings.sms_provider, "delivered": send_ok},
    )
    await db.commit()

    return generic_resp


@router.post("/phone/verify-otp", response_model=AuthTokenResponse)
async def verify_phone_otp(
    req: PhoneOtpVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    """Verify phone OTP with lockout protection and create/log-in user."""
    if not is_phone_auth_enabled(settings):
        raise ServiceUnavailableException(
            "Phone authentication is currently unavailable.",
            code="phone_login_disabled",
        )

    client_ip, user_agent = _get_request_meta(request)

    normalized_phone = normalize_phone_number(
        req.phone_number,
        allowlist=settings.sms_country_allowlist,
    )
    ident_hash = hash_identifier(normalized_phone)
    now = datetime.now(UTC)

    token_res = await db.execute(
        select(AuthToken)
        .where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.identifier_hash == ident_hash,
            AuthToken.is_used.is_(False),
        )
        .order_by(AuthToken.created_at.desc())
    )
    token = token_res.scalars().first()

    if token is None or ensure_utc(token.expires_at) < now or token.attempts_count >= token.max_attempts:
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.OTP_VERIFY_FAILURE,
            identifier=normalized_phone,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"reason": "expired_or_locked"},
        )
        await db.commit()
        raise ValidationException("Invalid or expired OTP.")

    # Constant-time HMAC comparison
    is_valid = verify_otp_hash(req.otp, token.token_hash, settings.jwt_secret_key)
    if not is_valid:
        token.attempts_count += 1
        if token.attempts_count >= token.max_attempts:
            token.is_used = True
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.OTP_VERIFY_FAILURE,
            identifier=normalized_phone,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"attempts": token.attempts_count},
        )
        await db.commit()
        raise ValidationException("Invalid or expired OTP.")

    # Successful OTP verification
    token.is_used = True

    # Find or create user
    ident_res = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == AuthProvider.PHONE,
            UserIdentity.provider_user_id == normalized_phone,
        )
    )
    identity = ident_res.scalar_one_or_none()

    if identity is not None:
        user_res = await db.execute(select(User).where(User.id == identity.user_id))
        user = user_res.scalar_one_or_none()
        if user is None or not user.is_active:
            raise UnauthorizedException("User account is inactive or not found.")
        identity.last_sign_in_at = now
    else:
        user_res = await db.execute(select(User).where(User.phone_number == normalized_phone))
        user = user_res.scalar_one_or_none()

        if user is None:
            user = User(
                email=None,
                normalized_email=None,
                hashed_password=None,
                full_name=req.full_name or "Phone User",
                phone_number=normalized_phone,
                is_active=True,
            )
            db.add(user)
            await db.flush()

            await log_auth_event(
                db=db,
                event_type=AuthAuditEventType.REGISTER,
                user_id=user.id,
                identifier=normalized_phone,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"method": "phone"},
            )

        identity = UserIdentity(
            user_id=user.id,
            provider=AuthProvider.PHONE,
            provider_user_id=normalized_phone,
            phone_number=normalized_phone,
            last_sign_in_at=now,
        )
        db.add(identity)

    access_token, refresh_token, _ = await create_user_session(
        db=db,
        user_id=user.id,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.OTP_VERIFY_SUCCESS,
        user_id=user.id,
        identifier=normalized_phone,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()

    consent_given = await _check_user_consent_given(db, user.id)
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=consent_given,
    )


# ============================================================================
# Password Reset & Email Verification
# ============================================================================


@router.post("/password-reset/request", response_model=MessageResponse)
async def request_password_reset(
    req: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Request a password reset link. Always returns a generic response (no enumeration)."""
    settings = get_settings()
    client_ip, user_agent = _get_request_meta(request)
    normalized_email = str(req.email).lower().strip()

    is_locked, lock_scope = lockout_tracker.is_reset_locked(normalized_email, client_ip)
    if is_locked:
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.PASSWORD_RESET_REQUEST,
            identifier=normalized_email,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"reason": "rate_limited", "scope": lock_scope},
        )
        await db.commit()
        return MessageResponse(
            message="If this email is registered, a password reset link has been sent.",
        )

    lockout_tracker.record_reset_request(normalized_email, client_ip)
    user_res = await db.execute(select(User).where(User.normalized_email == normalized_email))
    user = user_res.scalar_one_or_none()

    if user is not None and user.is_active:
        now = datetime.now(UTC)
        import secrets

        raw_token = secrets.token_urlsafe(32)
        token_hashed = hash_token(raw_token)
        ident_hash = hash_identifier(normalized_email)

        auth_token = AuthToken(
            identifier_hash=ident_hash,
            token_hash=token_hashed,
            token_type=AuthTokenType.PASSWORD_RESET,
            expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
            attempts_count=0,
            max_attempts=5,
            is_used=False,
        )
        db.add(auth_token)
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.PASSWORD_RESET_REQUEST,
            user_id=user.id,
            identifier=normalized_email,
            ip_address=client_ip,
            user_agent=user_agent,
        )
        await db.commit()

    return MessageResponse(
        message="If this email is registered, a password reset link has been sent.",
    )


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(
    req: PasswordResetConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Confirm password reset with single-use token and revoke all existing sessions."""
    client_ip, user_agent = _get_request_meta(request)
    now = datetime.now(UTC)
    token_hashed = hash_token(req.token)

    token_res = await db.execute(
        select(AuthToken).where(
            AuthToken.token_type == AuthTokenType.PASSWORD_RESET,
            AuthToken.token_hash == token_hashed,
            AuthToken.is_used.is_(False),
        )
    )
    token = token_res.scalar_one_or_none()

    if token is None or ensure_utc(token.expires_at) < now:
        raise ValidationException("Invalid or expired password reset token.")

    # Match user by identifier hash
    users_res = await db.execute(select(User))
    user_match = None
    for u in users_res.scalars().all():
        if u.normalized_email and hash_identifier(u.normalized_email) == token.identifier_hash:
            user_match = u
            break

    if user_match is None:
        raise ValidationException("User associated with this reset token was not found.")

    token.is_used = True
    user_match.hashed_password = hash_password(req.new_password)

    # Revoke ALL active sessions immediately upon password change
    await revoke_all_user_sessions(db, user_match.id)
    lockout_tracker.unlock_via_reset(user_match.normalized_email)

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.PASSWORD_RESET_SUCCESS,
        user_id=user_match.id,
        identifier=user_match.normalized_email,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"unlocked": True},
    )
    await db.commit()

    return MessageResponse(
        message="Password has been reset successfully. Please log in with your new password.",
    )


@router.post("/verify-email/request", response_model=MessageResponse)
async def request_email_verification(
    req: EmailVerifyRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Request an email verification link for the user."""
    settings = get_settings()
    client_ip, user_agent = _get_request_meta(request)
    email_to_verify = req.email or user.email

    if not email_to_verify:
        raise ValidationException("No email address provided for verification.")

    now = datetime.now(UTC)
    import secrets

    raw_token = secrets.token_urlsafe(32)
    token_hashed = hash_token(raw_token)
    ident_hash = hash_identifier(str(email_to_verify))

    auth_token = AuthToken(
        identifier_hash=ident_hash,
        token_hash=token_hashed,
        token_type=AuthTokenType.EMAIL_VERIFICATION,
        expires_at=now + timedelta(hours=settings.email_verification_token_expire_hours),
        attempts_count=0,
        max_attempts=5,
        is_used=False,
    )
    db.add(auth_token)

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.EMAIL_VERIFY_REQUEST,
        user_id=user.id,
        identifier=str(email_to_verify),
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()

    return MessageResponse(
        message="If this email is registered, a verification link has been sent.",
    )


@router.post("/verify-email/confirm", response_model=MessageResponse)
async def confirm_email_verification(
    req: EmailVerifyConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Confirm email verification token."""
    client_ip, user_agent = _get_request_meta(request)
    now = datetime.now(UTC)
    token_hashed = hash_token(req.token)

    token_res = await db.execute(
        select(AuthToken).where(
            AuthToken.token_type == AuthTokenType.EMAIL_VERIFICATION,
            AuthToken.token_hash == token_hashed,
            AuthToken.is_used.is_(False),
        )
    )
    token = token_res.scalar_one_or_none()

    if token is None or ensure_utc(token.expires_at) < now:
        raise ValidationException("Invalid or expired email verification token.")

    token.is_used = True
    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.EMAIL_VERIFY_SUCCESS,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()

    return MessageResponse(message="Email verified successfully.")


# ============================================================================
# Session Management & Token Rotation
# ============================================================================


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh_tokens(
    req: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    """Rotate opaque refresh token and issue new access token with reuse detection."""
    client_ip, user_agent = _get_request_meta(request)
    new_access, new_refresh, session_id = await rotate_refresh_token(
        db=db,
        raw_refresh_token=req.refresh_token,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    token_payload = decode_access_token(new_access)
    user_id_str = token_payload["sub"]
    user_res = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str)))
    user = user_res.scalar_one_or_none()

    if user is None:
        raise UnauthorizedException("User not found.")

    consent_given = await _check_user_consent_given(db, user.id)
    return AuthTokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=consent_given,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    req: LogoutRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Log out the current active session."""
    client_ip, user_agent = _get_request_meta(request)
    user_id = uuid.UUID(current_user.user_id)

    if req.refresh_token:
        r_hash = hash_token(req.refresh_token)
        s_res = await db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.refresh_token_hash == r_hash,
            )
        )
        session = s_res.scalar_one_or_none()
        if session is not None:
            session.is_revoked = True
            await db.commit()

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.LOGOUT,
        user_id=user_id,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    await db.commit()
    return MessageResponse(message="Logged out successfully.")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revoke all active sessions for the current user."""
    client_ip, user_agent = _get_request_meta(request)
    revoked_count = await revoke_all_user_sessions(db, user.id)

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.LOGOUT_ALL,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"revoked_count": revoked_count},
    )
    await db.commit()
    return MessageResponse(message="All active sessions have been revoked.")


@router.get("/sessions", response_model=list[UserSessionItem])
async def list_active_sessions(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSessionItem]:
    """List all active (unrevoked) sessions for the user."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.is_revoked.is_(False),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_active_at.desc())
    )
    sessions = result.scalars().all()
    return [
        UserSessionItem(
            id=str(s.id),
            created_at=s.created_at.isoformat(),
            last_active_at=s.last_active_at.isoformat(),
            user_agent=s.user_agent,
            ip_address_mask=s.ip_address_mask,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revoke one of caller's own sessions.
    
    Other users' session IDs return 404. Revoking current session acts as logout.
    """
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Session not found.")

    client_ip, user_agent = _get_request_meta(request)
    if not session.is_revoked:
        session.is_revoked = True
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.LOGOUT,
            user_id=user.id,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"session_id": str(session_id)},
        )
        await db.commit()

    is_current = current_user.session_id and str(session_id) == str(current_user.session_id)
    return MessageResponse(
        message="Current session logged out." if is_current else "Session revoked successfully."
    )


# ============================================================================
# Account Linking & Auth Methods
# ============================================================================


@router.get("/methods", response_model=AuthMethodsResponse)
async def list_auth_methods(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AuthMethodsResponse:
    """List all configured authentication methods for the user."""
    result = await db.execute(select(UserIdentity).where(UserIdentity.user_id == user.id))
    identities = result.scalars().all()

    items = [
        AuthMethodItem(
            id=str(ident.id),
            provider=ident.provider.value,
            identifier=ident.email or ident.phone_number or ident.provider_user_id,
            created_at=ident.created_at.isoformat(),
        )
        for ident in identities
    ]
    return AuthMethodsResponse(
        has_password=bool(user.hashed_password),
        methods=items,
    )


@router.delete("/link/{provider}", response_model=MessageResponse)
async def unlink_auth_method(
    provider: str,
    request: Request,
    user: User = Depends(require_recent_auth(600)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Unlink an authentication provider. Rejects removal of the sole remaining method. Requires recent auth."""
    client_ip, user_agent = _get_request_meta(request)
    result = await db.execute(select(UserIdentity).where(UserIdentity.user_id == user.id))
    identities = result.scalars().all()

    has_pwd = bool(user.hashed_password or any(i.provider == AuthProvider.PASSWORD for i in identities))
    has_google = any(i.provider == AuthProvider.GOOGLE for i in identities)
    has_phone = any(i.provider == AuthProvider.PHONE for i in identities)

    available_methods: set[str] = set()
    if has_pwd:
        available_methods.add("password")
    if has_google:
        available_methods.add("google")
    if has_phone:
        available_methods.add("phone")

    if provider not in available_methods:
        raise ValidationException(f"No authentication method linked with provider '{provider}'.")

    # Safety guard: Never remove the user's last remaining authentication method!
    if len(available_methods) <= 1:
        raise ValidationException("Cannot remove your sole authentication method.")

    if provider == "password":
        user.hashed_password = None
        for m in identities:
            if m.provider == AuthProvider.PASSWORD:
                await db.execute(delete(UserIdentity).where(UserIdentity.id == m.id))
    else:
        for m in identities:
            if m.provider.value == provider:
                await db.execute(delete(UserIdentity).where(UserIdentity.id == m.id))

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.IDENTITY_UNLINKED,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"provider": provider},
    )
    await db.commit()

    return MessageResponse(message=f"Authentication method '{provider}' unlinked successfully.")


@router.post("/link/google", response_model=MessageResponse)
async def link_google_account(
    req: GoogleAuthRequest,
    request: Request,
    user: User = Depends(require_recent_auth(600)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Link Google identity to currently authenticated user. Requires recent auth (<= 10 min)."""
    client_ip, user_agent = _get_request_meta(request)
    payload = verify_google_id_token(req.id_token)

    if not payload.get("email_verified"):
        raise ValidationException("Google account email is not verified.")

    sub = str(payload["sub"])
    email = str(payload["email"]).lower().strip()

    # Check if Google sub is linked anywhere
    ident_res = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == AuthProvider.GOOGLE,
            UserIdentity.provider_user_id == sub,
        )
    )
    existing_ident = ident_res.scalar_one_or_none()

    if existing_ident is not None:
        if existing_ident.user_id == user.id:
            return MessageResponse(message="Google account is already linked.")
        raise ConflictException("This Google account cannot be linked.")

    # Check if user already has a Google identity
    user_google = await db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == user.id,
            UserIdentity.provider == AuthProvider.GOOGLE,
        )
    )
    if user_google.scalar_one_or_none() is not None:
        raise ConflictException("A Google account is already linked to this account.")

    identity = UserIdentity(
        user_id=user.id,
        provider=AuthProvider.GOOGLE,
        provider_user_id=sub,
        email=email,
        last_sign_in_at=datetime.now(UTC),
    )
    db.add(identity)
    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.IDENTITY_LINKED,
        user_id=user.id,
        identifier=email,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"provider": "google"},
    )
    await db.commit()
    return MessageResponse(message="Google account linked successfully.")


@router.post("/link/phone", response_model=MessageResponse)
@router.post("/link/phone/request-otp", response_model=MessageResponse)
async def request_link_phone_otp(
    req: PhoneLinkRequest,
    request: Request,
    user: User = Depends(require_recent_auth(600)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Request OTP to link phone number to account. Requires recent auth and honors capabilities flag."""
    if not is_phone_auth_enabled(settings):
        raise ServiceUnavailableException(
            "Phone authentication is currently unavailable.",
            code="phone_login_disabled",
        )

    # If OTP is already provided in the request body, delegate to verify step
    if req.otp:
        return await verify_link_phone_otp(
            req=PhoneOtpVerifyRequest(phone_number=req.phone_number, otp=req.otp),
            request=request,
            user=user,
            db=db,
            settings=settings,
        )

    client_ip, user_agent = _get_request_meta(request)
    normalized_phone = normalize_phone_number(
        req.phone_number,
        allowlist=settings.sms_country_allowlist,
    )

    # Conflict check: is phone linked to another user?
    other_ident = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == AuthProvider.PHONE,
            UserIdentity.provider_user_id == normalized_phone,
            UserIdentity.user_id != user.id,
        )
    )
    if other_ident.scalar_one_or_none() is not None:
        raise ConflictException("This phone number cannot be linked.")

    other_user = await db.execute(
        select(User).where(
            User.phone_number == normalized_phone,
            User.id != user.id,
        )
    )
    if other_user.scalar_one_or_none() is not None:
        raise ConflictException("This phone number cannot be linked.")

    # Check if already linked to THIS user
    own_ident = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == AuthProvider.PHONE,
            UserIdentity.user_id == user.id,
        )
    )
    if own_ident.scalar_one_or_none() is not None:
        raise ConflictException("A phone number is already linked to this account.")

    # Rate limiting & OTP Generation
    ident_hash = hash_identifier(normalized_phone)
    now = datetime.now(UTC)
    cooldown = timedelta(seconds=settings.otp_cooldown_seconds)

    recent_token_res = await db.execute(
        select(AuthToken)
        .where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.identifier_hash == ident_hash,
            AuthToken.created_at > (now - cooldown),
        )
    )
    if recent_token_res.scalars().first() is not None:
        raise ValidationException("Please wait before requesting another OTP.")

    one_day_ago = now - timedelta(days=1)
    daily_count_res = await db.execute(
        select(func.count(AuthToken.id)).where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.created_at >= one_day_ago,
        )
    )
    daily_count = daily_count_res.scalar() or 0
    effective_cap = min(settings.sms_daily_cap, settings.otp_daily_global_cap)
    if daily_count >= effective_cap:
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.OTP_REQUEST,
            identifier=normalized_phone,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"error": "daily_cap_exceeded"},
        )
        await db.commit()
        raise ServiceUnavailableException(
            "SMS service is currently unavailable. Please try again tomorrow.",
            code="sms_daily_cap_exceeded",
        )

    otp_code = generate_otp()
    otp_hash = hash_otp(otp_code, settings.jwt_secret_key)
    expires_at = now + timedelta(seconds=settings.otp_expiry_seconds)

    token = AuthToken(
        identifier_hash=ident_hash,
        token_hash=otp_hash,
        token_type=AuthTokenType.OTP,
        expires_at=expires_at,
        attempts_count=0,
        max_attempts=settings.otp_max_attempts,
        is_used=False,
    )
    db.add(token)

    sms_provider = get_sms_provider(settings)
    await sms_provider.send_otp(normalized_phone, otp_code)

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.OTP_REQUEST,
        identifier=normalized_phone,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"purpose": "link"},
    )
    await db.commit()
    return MessageResponse(
        message="OTP sent to phone.",
        cooldown_seconds=settings.otp_cooldown_seconds,
    )


@router.post("/link/phone/verify-otp", response_model=MessageResponse)
async def verify_link_phone_otp(
    req: PhoneOtpVerifyRequest,
    request: Request,
    user: User = Depends(require_recent_auth(600)),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """Verify phone OTP and link to account. Requires recent auth."""
    if not is_phone_auth_enabled(settings):
        raise ServiceUnavailableException(
            "Phone authentication is currently unavailable.",
            code="phone_login_disabled",
        )

    client_ip, user_agent = _get_request_meta(request)
    normalized_phone = normalize_phone_number(
        req.phone_number,
        allowlist=settings.sms_country_allowlist,
    )
    ident_hash = hash_identifier(normalized_phone)
    now = datetime.now(UTC)

    token_res = await db.execute(
        select(AuthToken)
        .where(
            AuthToken.token_type == AuthTokenType.OTP,
            AuthToken.identifier_hash == ident_hash,
            AuthToken.is_used.is_(False),
        )
        .order_by(AuthToken.created_at.desc())
    )
    token = token_res.scalars().first()

    if token is None or ensure_utc(token.expires_at) < now or token.attempts_count >= token.max_attempts:
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.OTP_VERIFY_FAILURE,
            identifier=normalized_phone,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"purpose": "link", "reason": "expired_or_locked"},
        )
        await db.commit()
        raise ValidationException("Invalid or expired OTP.")

    is_valid = verify_otp_hash(req.otp, token.token_hash, settings.jwt_secret_key)
    if not is_valid:
        token.attempts_count += 1
        if token.attempts_count >= token.max_attempts:
            token.is_used = True
        await log_auth_event(
            db=db,
            event_type=AuthAuditEventType.OTP_VERIFY_FAILURE,
            identifier=normalized_phone,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata={"purpose": "link", "attempts": token.attempts_count},
        )
        await db.commit()
        raise ValidationException("Invalid or expired OTP.")

    token.is_used = True

    # Re-verify conflict
    other_ident = await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == AuthProvider.PHONE,
            UserIdentity.provider_user_id == normalized_phone,
            UserIdentity.user_id != user.id,
        )
    )
    if other_ident.scalar_one_or_none() is not None:
        raise ConflictException("This phone number cannot be linked.")

    identity = UserIdentity(
        user_id=user.id,
        provider=AuthProvider.PHONE,
        provider_user_id=normalized_phone,
        phone_number=normalized_phone,
        last_sign_in_at=now,
    )
    db.add(identity)
    if user.phone_number is None:
        user.phone_number = normalized_phone

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.IDENTITY_LINKED,
        user_id=user.id,
        identifier=normalized_phone,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"provider": "phone"},
    )
    await db.commit()
    return MessageResponse(message="Phone number linked successfully.")


@router.post("/password", response_model=MessageResponse)
async def set_initial_password(
    req: SetPasswordRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    user: User = Depends(require_recent_auth(600)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Set an initial password for accounts without one. Revokes other active sessions. Requires recent auth."""
    if user.hashed_password is not None:
        raise ConflictException("Account already has a password set. Use password reset or change password.")

    if len(req.password) < 8:
        raise ValidationException("Password must be at least 8 characters long.")

    client_ip, user_agent = _get_request_meta(request)
    user.hashed_password = hash_password(req.password)

    ident_res = await db.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == user.id,
            UserIdentity.provider == AuthProvider.PASSWORD,
        )
    )
    if ident_res.scalar_one_or_none() is None:
        db.add(
            UserIdentity(
                user_id=user.id,
                provider=AuthProvider.PASSWORD,
                provider_user_id=user.normalized_email or user.email or str(user.id),
                email=user.email,
                last_sign_in_at=datetime.now(UTC),
            )
        )

    # Revoke all OTHER sessions belonging to this user
    if current_user.session_id:
        try:
            curr_sid = uuid.UUID(current_user.session_id)
            await db.execute(
                update(UserSession)
                .where(
                    UserSession.user_id == user.id,
                    UserSession.id != curr_sid,
                    UserSession.is_revoked.is_(False),
                )
                .values(is_revoked=True)
            )
        except (ValueError, TypeError):
            pass

    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.PASSWORD_RESET_SUCCESS,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"action": "set_password"},
    )
    await db.commit()
    return MessageResponse(message="Password set successfully. Other active sessions have been revoked.")


@router.post("/reauth", response_model=AuthTokenResponse)
async def reauthenticate(
    req: ReauthRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthTokenResponse:
    """Re-authenticate with password, Google ID token, or phone OTP to renew recent auth status."""
    client_ip, user_agent = _get_request_meta(request)
    now = datetime.now(UTC)

    if req.method == "password":
        if not user.hashed_password or not req.password:
            raise UnauthorizedException("Invalid password.")
        if not verify_password(req.password, user.hashed_password):
            raise UnauthorizedException("Invalid password.")

    elif req.method == "google":
        if not req.id_token:
            raise UnauthorizedException("Missing Google ID token.")
        payload = verify_google_id_token(req.id_token)
        sub = str(payload.get("sub"))
        ident = await db.execute(
            select(UserIdentity).where(
                UserIdentity.user_id == user.id,
                UserIdentity.provider == AuthProvider.GOOGLE,
                UserIdentity.provider_user_id == sub,
            )
        )
        if ident.scalar_one_or_none() is None:
            raise UnauthorizedException("Google identity does not match this account.")

    elif req.method == "phone":
        if not is_phone_auth_enabled(settings):
            raise ServiceUnavailableException("Phone authentication is disabled.", code="phone_login_disabled")
        if not req.phone_number or not req.otp:
            raise UnauthorizedException("Phone number and OTP are required.")
        normalized_phone = normalize_phone_number(req.phone_number, allowlist=settings.sms_country_allowlist)
        ident = await db.execute(
            select(UserIdentity).where(
                UserIdentity.user_id == user.id,
                UserIdentity.provider == AuthProvider.PHONE,
                UserIdentity.provider_user_id == normalized_phone,
            )
        )
        if ident.scalar_one_or_none() is None:
            raise UnauthorizedException("Phone identity does not match this account.")

        ident_hash = hash_identifier(normalized_phone)
        token_res = await db.execute(
            select(AuthToken)
            .where(
                AuthToken.token_type == AuthTokenType.OTP,
                AuthToken.identifier_hash == ident_hash,
                AuthToken.is_used.is_(False),
            )
            .order_by(AuthToken.created_at.desc())
        )
        token = token_res.scalars().first()
        if token is None or ensure_utc(token.expires_at) < now or token.attempts_count >= token.max_attempts:
            raise ValidationException("Invalid or expired OTP.")
        if not verify_otp_hash(req.otp, token.token_hash, settings.jwt_secret_key):
            token.attempts_count += 1
            if token.attempts_count >= token.max_attempts:
                token.is_used = True
            await db.commit()
            raise ValidationException("Invalid or expired OTP.")
        token.is_used = True
    else:
        raise ValidationException("Unsupported re-authentication method.")

    access_token, refresh_token, _ = await create_user_session(
        db=db,
        user_id=user.id,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    await log_auth_event(
        db=db,
        event_type=AuthAuditEventType.LOGIN_SUCCESS,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
        metadata={"reauth": True, "method": req.method},
    )
    await db.commit()
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=True,
    )


# ============================================================================
# Profile & Consent
# ============================================================================


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Retrieve currently authenticated user profile and consent settings."""
    result = await db.execute(
        select(Consent).where(
            Consent.user_id == user.id,
            Consent.revoked_at.is_(None),
        )
    )
    active_consents = {consent.consent_type: consent for consent in result.scalars().all()}
    terms = active_consents.get(ConsentType.TERMS)
    privacy = active_consents.get(ConsentType.PRIVACY)
    ai_processing = active_consents.get(ConsentType.AI_DATA_PROCESSING)

    return UserProfileResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        phone_number=user.phone_number,
        consent={
            "terms_accepted": terms is not None,
            "privacy_accepted": privacy is not None,
            "ai_data_processing_consent": ai_processing is not None,
            "consent_version": terms.consent_version if terms else (privacy.consent_version if privacy else "v1.0"),
            "consented_at": terms.granted_at.isoformat() if terms else None,
        },
    )


@router.post("/consent")
async def update_consent(
    req: ConsentUpdateRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update user terms, privacy, and AI data processing consent separately."""
    now = datetime.now(UTC)
    client_ip, _ = _get_request_meta(request)
    masked_ip = mask_ip_address(client_ip)

    result = await db.execute(
        select(Consent).where(
            Consent.user_id == user.id,
            Consent.revoked_at.is_(None),
        )
    )
    active_consents = {consent.consent_type: consent for consent in result.scalars().all()}

    consent_values = (
        (ConsentType.TERMS, req.terms_accepted),
        (ConsentType.PRIVACY, req.privacy_accepted),
        (ConsentType.AI_DATA_PROCESSING, req.ai_data_processing_consent),
    )
    for consent_type, accepted in consent_values:
        existing = active_consents.get(consent_type)
        if accepted and existing is None:
            db.add(
                Consent(
                    user_id=user.id,
                    consent_type=consent_type,
                    consent_version=req.consent_version,
                    granted_at=now,
                    ip_address_mask=masked_ip,
                )
            )
        elif not accepted and existing is not None:
            existing.revoked_at = now

    await db.commit()
    return {
        "status": "updated",
        "user_id": str(user.id),
        "consent": {
            "terms_accepted": req.terms_accepted,
            "privacy_accepted": req.privacy_accepted,
            "ai_data_processing_consent": req.ai_data_processing_consent,
            "consent_version": req.consent_version,
            "updated_at": now.isoformat(),
        },
    }
