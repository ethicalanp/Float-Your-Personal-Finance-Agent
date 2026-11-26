import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime

from app.core.errors import ValidationException


def ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_phone_number(raw_phone: str, default_country: str = "+91", allowlist: str = "+91") -> str:
    """Normalize a raw phone string into E.164 format and validate against allowlist."""
    cleaned = re.sub(r"[\s\-\(\)\.]", "", raw_phone)
    if not cleaned:
        raise ValidationException("Phone number cannot be empty.")

    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    elif cleaned.startswith("0"):
        cleaned = default_country + cleaned[1:]
    elif not cleaned.startswith("+"):
        if len(cleaned) == 10:
            cleaned = default_country + cleaned
        else:
            cleaned = "+" + cleaned

    # Validate E.164 pattern: + followed by 10-15 digits
    if not re.match(r"^\+[1-9]\d{9,14}$", cleaned):
        raise ValidationException("Invalid phone number format. Must be a valid E.164 number.")

    # Validate country allowlist
    allowed_prefixes = [p.strip() for p in allowlist.split(",") if p.strip()]
    if allowed_prefixes and not any(cleaned.startswith(p) for p in allowed_prefixes):
        raise ValidationException(f"Phone country prefix is not permitted. Allowed: {allowlist}")

    return cleaned


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    upper = 10**length
    val = secrets.randbelow(upper)
    return f"{val:0{length}d}"


def hash_otp(otp: str, secret_key: str) -> str:
    """HMAC-SHA256 hash of an OTP code using the secret key."""
    return hmac.new(secret_key.encode("utf-8"), otp.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp_hash(candidate_otp: str, expected_hash: str, secret_key: str) -> bool:
    """Constant-time verification of candidate OTP against stored HMAC hash."""
    candidate_hash = hash_otp(candidate_otp, secret_key)
    return secrets.compare_digest(candidate_hash, expected_hash)


def hash_identifier(identifier: str) -> str:
    """One-way SHA-256 hash of a normalized email or phone number for audit/lookup."""
    return hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()


def mask_ip_address(ip: str | None) -> str | None:
    """Mask an IP address to preserve privacy while enabling abuse analysis."""
    if not ip:
        return None
    ip_clean = ip.strip()
    if ":" in ip_clean:
        # IPv6: retain first 3 blocks
        parts = ip_clean.split(":")
        return ":".join(parts[:3]) + "::xxxx"
    parts = ip_clean.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    return "xxx.xxx.xxx.xxx"
