from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.core.errors import ConflictException, UnauthorizedException
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.enums import ConsentType
from app.models.user import Consent, User

router = APIRouter(prefix="/auth", tags=["Authentication & Consent"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    terms_accepted: bool = False
    ai_data_processing_consent: bool = False
    consent_version: str = "v1.0"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    consent_given: bool


class ConsentUpdateRequest(BaseModel):
    terms_accepted: bool
    ai_data_processing_consent: bool
    consent_version: str = "v1.0"


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    consent: dict[str, Any]


@router.post("/register", response_model=AuthTokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)) -> AuthTokenResponse:
    """Register a new user, capture required privacy consent, and issue an access token."""
    normalized_email = req.email.lower().strip()

    # Check for existing user
    stmt = select(User).where(User.normalized_email == normalized_email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
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

    # Add active consents if consented
    now = datetime.now(UTC)
    if req.terms_accepted:
        terms_consent = Consent(
            user_id=user.id,
            consent_type=ConsentType.TERMS,
            consent_version=req.consent_version,
            granted_at=now,
        )
        db.add(terms_consent)

    if req.ai_data_processing_consent:
        ai_consent = Consent(
            user_id=user.id,
            consent_type=ConsentType.AI_DATA_PROCESSING,
            consent_version=req.consent_version,
            granted_at=now,
        )
        db.add(ai_consent)

    await db.commit()
    await db.refresh(user)

    token = create_access_token(subject=str(user.id))
    consent_given = bool(req.terms_accepted and req.ai_data_processing_consent)

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=consent_given,
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)) -> AuthTokenResponse:
    """Authenticate with email and password, returning an access token."""
    normalized_email = req.email.lower().strip()

    stmt = select(User).where(User.normalized_email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise UnauthorizedException("Invalid email or password.")
    if not user.is_active:
        raise UnauthorizedException("User account is inactive.")

    # Check active consent status
    consent_stmt = select(Consent).where(
        Consent.user_id == user.id,
        Consent.revoked_at.is_(None),
    )
    consent_result = await db.execute(consent_stmt)
    active_consents = {c.consent_type for c in consent_result.scalars().all()}
    consent_given = bool(
        ConsentType.TERMS in active_consents and ConsentType.AI_DATA_PROCESSING in active_consents
    )

    token = create_access_token(subject=str(user.id))

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent_given=consent_given,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Retrieve currently authenticated user profile and consent settings."""
    consent_stmt = select(Consent).where(
        Consent.user_id == user.id,
        Consent.revoked_at.is_(None),
    )
    consent_result = await db.execute(consent_stmt)
    active_consents = {c.consent_type: c for c in consent_result.scalars().all()}

    terms = active_consents.get(ConsentType.TERMS)
    ai_proc = active_consents.get(ConsentType.AI_DATA_PROCESSING)

    consent_dict = {
        "terms_accepted": terms is not None,
        "ai_data_processing_consent": ai_proc is not None,
        "consent_version": terms.consent_version if terms else "v1.0",
        "consented_at": terms.granted_at.isoformat() if terms else None,
    }

    return UserProfileResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        consent=consent_dict,
    )


@router.post("/consent")
async def update_consent(
    req: ConsentUpdateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update user privacy and AI data processing consent."""
    now = datetime.now(UTC)

    # Fetch existing active consents
    consent_stmt = select(Consent).where(
        Consent.user_id == user.id,
        Consent.revoked_at.is_(None),
    )
    consent_result = await db.execute(consent_stmt)
    active_map = {c.consent_type: c for c in consent_result.scalars().all()}

    # Update TERMS
    if req.terms_accepted and ConsentType.TERMS not in active_map:
        db.add(
            Consent(
                user_id=user.id,
                consent_type=ConsentType.TERMS,
                consent_version=req.consent_version,
                granted_at=now,
            )
        )
    elif not req.terms_accepted and ConsentType.TERMS in active_map:
        active_map[ConsentType.TERMS].revoked_at = now

    # Update AI_DATA_PROCESSING
    if req.ai_data_processing_consent and ConsentType.AI_DATA_PROCESSING not in active_map:
        db.add(
            Consent(
                user_id=user.id,
                consent_type=ConsentType.AI_DATA_PROCESSING,
                consent_version=req.consent_version,
                granted_at=now,
            )
        )
    elif not req.ai_data_processing_consent and ConsentType.AI_DATA_PROCESSING in active_map:
        active_map[ConsentType.AI_DATA_PROCESSING].revoked_at = now

    await db.commit()

    return {
        "status": "updated",
        "user_id": str(user.id),
        "consent": {
            "terms_accepted": req.terms_accepted,
            "ai_data_processing_consent": req.ai_data_processing_consent,
            "consent_version": req.consent_version,
            "updated_at": now.isoformat(),
        },
    }
