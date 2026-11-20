import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import UnauthorizedException

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a plaintext password with a random 16-byte salt using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations=100_000,
    )
    return f"pbkdf2:sha256:100000${salt.hex()}${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored PBKDF2 hash."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        meta, salt_hex, key_hex = parts
        _, _, iterations_str = meta.split(":")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)

        computed_key = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            iterations=iterations,
        )
        return hmac.compare_digest(computed_key, expected_key)
    except Exception:
        return False


def create_access_token(
    subject: str,
    expires_minutes: int | None = None,
) -> str:
    """Create a minimal HS256-signed JWT token via PyJWT.

    Minimal claims principle: carries only subject identity (user_id), iat, exp, and jti.
    Sensitive profile and consent details are queried fresh from the database.
    """
    settings = get_settings()
    exp_minutes = expires_minutes or settings.jwt_access_token_expire_minutes
    now = datetime.now(timezone.utc)
    exp = int(now.timestamp()) + (exp_minutes * 60)

    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": exp,
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Safely decode and verify JWT token using PyJWT. Never raises 500 on malformed input."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
        return payload
    except jwt.ExpiredSignatureError as err:
        raise UnauthorizedException("Authentication token has expired") from err
    except jwt.PyJWTError as err:
        raise UnauthorizedException("Invalid authentication token") from err
    except Exception as err:
        raise UnauthorizedException("Could not validate authentication credentials") from err


class CurrentUser(BaseModel):
    user_id: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """Dependency extracting and validating the authenticated user from the Bearer token."""
    if not credentials:
        raise UnauthorizedException("Missing Authorization header")

    payload = decode_access_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedException("Invalid token subject")

    return CurrentUser(user_id=str(sub))
