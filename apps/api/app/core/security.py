import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Header
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import UnauthorizedException


def hash_password(password: str) -> str:
    """Hash a plaintext password with a random 16-byte salt using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations=100_000,
    )
    # Store format: algorithm$iterations$salt_hex$key_hex
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


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding and padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def create_access_token(
    subject: str,
    claims: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Create a standard HS256-signed JWT token."""
    settings = get_settings()
    exp_minutes = expires_minutes or settings.jwt_access_token_expire_minutes
    now = int(time.time())
    exp = now + (exp_minutes * 60)

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "iat": now,
        "exp": exp,
    }
    if claims:
        payload.update(claims)

    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    encoded_signature = _b64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a standard HS256-signed JWT token."""
    settings = get_settings()
    parts = token.split(".")
    if len(parts) != 3:
        raise UnauthorizedException("Invalid token format")

    encoded_header, encoded_payload, encoded_signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")

    expected_signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    actual_signature = _b64url_decode(encoded_signature)
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise UnauthorizedException("Token signature verification failed")

    payload_bytes = _b64url_decode(encoded_payload)
    payload = json.loads(payload_bytes.decode("utf-8"))

    now = int(time.time())
    if payload.get("exp") and now > payload["exp"]:
        raise UnauthorizedException("Token has expired")

    return payload


class CurrentUser(BaseModel):
    user_id: str
    email: str
    full_name: str
    consent_given: bool = False


async def get_current_user(authorization: str | None = Header(None)) -> CurrentUser:
    """Dependency to extract and validate the authenticated user from the Authorization header."""
    if not authorization:
        raise UnauthorizedException("Missing Authorization header")

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedException("Authorization header must be 'Bearer <token>'")

    token = parts[1]
    payload = decode_access_token(token)

    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedException("Invalid token payload")

    return CurrentUser(
        user_id=sub,
        email=payload.get("email", ""),
        full_name=payload.get("full_name", ""),
        consent_given=payload.get("consent_given", False),
    )
