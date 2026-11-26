import logging
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.errors import UnauthorizedException, ValidationException

logger = logging.getLogger(__name__)

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Verify Google ID token signature, issuer, audience, expiry, and email_verified."""
    settings = get_settings()

    allowed_audiences = []
    if settings.google_client_id:
        allowed_audiences.append(settings.google_client_id)
    if settings.google_client_ids:
        allowed_audiences.extend(
            [aud.strip() for aud in settings.google_client_ids.split(",") if aud.strip()]
        )

    # For testing and dev mock tokens
    if settings.app_env in ("test", "development"):
        try:
            # First check if it's signed with HS256 for unit tests
            unverified_header = jwt.get_unverified_header(id_token)
            if unverified_header.get("alg") == "HS256":
                payload = jwt.decode(
                    id_token,
                    settings.jwt_secret_key,
                    algorithms=["HS256"],
                    options={"verify_aud": False},
                )
                _validate_google_claims(payload, allowed_audiences)
                return payload
        except (UnauthorizedException, ValidationException):
            raise
        except Exception:
            pass

    try:
        jwks_client = PyJWKClient(GOOGLE_JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=list(GOOGLE_ISSUERS),
            options={"verify_aud": bool(allowed_audiences)},
            audience=allowed_audiences if allowed_audiences else None,
        )
        _validate_google_claims(payload, allowed_audiences)
        return payload
    except jwt.PyJWTError as e:
        logger.warning("Google ID token verification failed: %s", type(e).__name__)
        raise UnauthorizedException("Invalid or expired Google ID token.") from e


def _validate_google_claims(payload: dict[str, Any], allowed_audiences: list[str]) -> None:
    # 1. Issuer check
    iss = payload.get("iss")
    if iss not in GOOGLE_ISSUERS:
        logger.warning("Google ID token issuer rejected: %s", iss)
        raise UnauthorizedException("Invalid or expired Google ID token.")

    # 2. Audience check if configured
    if allowed_audiences and payload.get("aud") not in allowed_audiences:
        raise UnauthorizedException("Google token audience mismatch.")

    # 3. Subject check
    if not payload.get("sub"):
        raise ValidationException("Google token missing 'sub' subject claim.")

    # 4. Email check
    email = payload.get("email")
    if not email:
        raise ValidationException("Google token missing email claim.")

    # 5. email_verified MUST be strictly True - NEVER link unverified emails!
    email_verified = payload.get("email_verified")
    if email_verified is not True:
        raise ValidationException(
            "Google account email is not verified. Unverified emails cannot be used for sign-in or linking."
        )
