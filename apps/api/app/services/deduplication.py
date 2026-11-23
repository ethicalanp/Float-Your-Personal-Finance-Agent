import hashlib
import re
from datetime import datetime


def normalize_description(description: str) -> str:
    """Normalize transaction description by lowercasing, stripping extra spaces and punctuation."""
    if not description:
        return ""
    cleaned = description.lower()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return " ".join(cleaned.split())


def compute_transaction_fingerprint(
    account_id: str,
    date: datetime,
    amount: float,
    transaction_type: str,
    description: str,
) -> str:
    """Generate a deterministic SHA-256 fingerprint for duplicate detection."""
    date_str = date.strftime("%Y-%m-%d")
    norm_desc = normalize_description(description)
    raw_key = f"{account_id}:{date_str}:{amount:.2f}:{transaction_type.lower()}:{norm_desc}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
