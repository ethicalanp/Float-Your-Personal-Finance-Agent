import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from app.core.errors import ConflictException, UnauthorizedException
from app.core.security import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Consent"])

# In-memory storage for testability & dev environments
_USERS_DB: dict[str, dict[str, Any]] = {}
_CONSENTS_DB: dict[str, dict[str, Any]] = {}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    terms_accepted: bool = True
    ai_data_processing_consent: bool = True
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
async def register(req: RegisterRequest) -> AuthTokenResponse:
    """Register a new user, capture required privacy consent, and issue an access token."""
    email_lower = req.email.lower()
    if email_lower in _USERS_DB:
        raise ConflictException("A user with this email address already exists.")

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(req.password)
    now = datetime.now(UTC).isoformat()

    _USERS_DB[email_lower] = {
        "user_id": user_id,
        "email": email_lower,
        "full_name": req.full_name,
        "password_hash": pw_hash,
        "created_at": now,
    }

    _CONSENTS_DB[user_id] = {
        "terms_accepted": req.terms_accepted,
        "ai_data_processing_consent": req.ai_data_processing_consent,
        "consent_version": req.consent_version,
        "consented_at": now,
    }

    token = create_access_token(
        subject=user_id,
        claims={
            "email": email_lower,
            "full_name": req.full_name,
            "consent_given": req.terms_accepted and req.ai_data_processing_consent,
        },
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_id,
        email=email_lower,
        full_name=req.full_name,
        consent_given=req.terms_accepted and req.ai_data_processing_consent,
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(req: LoginRequest) -> AuthTokenResponse:
    """Authenticate with email and password, returning an access token."""
    email_lower = req.email.lower()
    user = _USERS_DB.get(email_lower)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise UnauthorizedException("Invalid email or password.")

    user_id = user["user_id"]
    consent = _CONSENTS_DB.get(user_id, {})
    consent_given = consent.get("terms_accepted", False) and consent.get("ai_data_processing_consent", False)

    token = create_access_token(
        subject=user_id,
        claims={
            "email": email_lower,
            "full_name": user["full_name"],
            "consent_given": consent_given,
        },
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_id,
        email=email_lower,
        full_name=user["full_name"],
        consent_given=consent_given,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: CurrentUser = Depends(get_current_user)) -> UserProfileResponse:
    """Retrieve currently authenticated user profile and consent settings."""
    consent = _CONSENTS_DB.get(current_user.user_id, {
        "terms_accepted": False,
        "ai_data_processing_consent": False,
        "consent_version": "v1.0",
        "consented_at": datetime.now(UTC).isoformat(),
    })

    return UserProfileResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        consent=consent,
    )


@router.post("/consent")
async def update_consent(
    req: ConsentUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Update user privacy and AI data processing consent."""
    now = datetime.now(UTC).isoformat()
    _CONSENTS_DB[current_user.user_id] = {
        "terms_accepted": req.terms_accepted,
        "ai_data_processing_consent": req.ai_data_processing_consent,
        "consent_version": req.consent_version,
        "consented_at": now,
    }
    return {
        "status": "updated",
        "user_id": current_user.user_id,
        "consent": _CONSENTS_DB[current_user.user_id],
    }
