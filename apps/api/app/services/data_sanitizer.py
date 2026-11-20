import asyncio
import re

MAX_SANITIZATION_LENGTH = 50_000

# Regex patterns for sensitive financial and PII elements in India
# Card: 16 digits formatted as 4-4-4-4 with spaces/hyphens or continuous
CARD_REGEX = re.compile(r"\b(?:\d{4}[\s\-]){3}\d{4}\b|\b\d{16}\b")

# Aadhaar: 12 digits, often formatted as 4-4-4 with spaces or hyphens (e.g., 1234 5678 9012)
AADHAAR_REGEX = re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b|\b(?<!\d)[2-9]\d{11}(?!\d)\b")

# PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_REGEX = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# UPI IDs: handle@psp (e.g. name@okhdfcbank, 9876543210@paytm)
UPI_REGEX = re.compile(r"\b[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}\b")

# Email addresses
EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

# Phone: Indian 10-digit mobile numbers (+91 prefix optional, space/hyphen between groups allowed)
# Handles: "+91 98765 43210", "+919876543210", "9876543210", "+91-98765-43210"
PHONE_REGEX = re.compile(
    r"(?:\+?91[\s\-]?)?(?<!\d)[6-9]\d{2,4}[\s\-]?\d{3,5}(?!\d)"
)

# Bank Account: 10 to 18 continuous digits
ACCOUNT_REGEX = re.compile(r"(?<!\d)\d{10,18}(?!\d)")


def mask_card(match: re.Match) -> str:
    raw = re.sub(r"[\s\-]", "", match.group(0))
    if len(raw) == 16:
        return f"****-****-****-{raw[-4:]}"
    return "****"


def mask_aadhaar(match: re.Match) -> str:
    raw = re.sub(r"[\s\-]", "", match.group(0))
    return f"XXXX-XXXX-{raw[-4:]}"


def mask_phone(match: re.Match) -> str:
    raw = re.sub(r"[\s\-]", "", match.group(0))
    if raw.startswith("+91"):
        raw = raw[3:]
    elif raw.startswith("91") and len(raw) == 12:
        raw = raw[2:]
    if len(raw) == 10:
        return f"+91-XXXXX-XX{raw[-3:]}"
    return "+91-XXXXXXXXXX"


def mask_account(match: re.Match) -> str:
    val = match.group(0)
    last4 = val[-4:]
    return f"****{last4}"


def mask_upi(match: re.Match) -> str:
    val = match.group(0)
    user_handle, handle_bank = val.split("@", 1)
    if len(user_handle) <= 2:
        masked_user = user_handle[0] + "*"
    else:
        masked_user = user_handle[0] + "***" + user_handle[-1]
    return f"{masked_user}@{handle_bank}"


def mask_email(match: re.Match) -> str:
    val = match.group(0)
    name, domain = val.split("@", 1)
    if len(name) <= 2:
        masked_name = name[0] + "*"
    else:
        masked_name = name[0] + "***" + name[-1]
    return f"{masked_name}@{domain}"


def mask_pan(match: re.Match) -> str:
    val = match.group(0)
    return f"XXXXX{val[5:9]}X"


def mask_sensitive_data(text: str) -> str:
    """Synchronously sanitize and redact sensitive PII and financial records.

    Caps scan length to MAX_SANITIZATION_LENGTH to prevent ReDoS / CPU freezing.
    """
    if not text:
        return ""

    # Enforce safe upper bound on single scan length
    if len(text) > MAX_SANITIZATION_LENGTH:
        text = text[:MAX_SANITIZATION_LENGTH]

    sanitized = text

    # 1. 16-digit Payment Cards
    sanitized = CARD_REGEX.sub(mask_card, sanitized)

    # 2. 12-digit Aadhaar (spaced and unspaced)
    sanitized = AADHAAR_REGEX.sub(mask_aadhaar, sanitized)

    # 3. PAN
    sanitized = PAN_REGEX.sub(mask_pan, sanitized)

    # 4. UPI IDs
    sanitized = UPI_REGEX.sub(mask_upi, sanitized)

    # 5. Email Addresses
    sanitized = EMAIL_REGEX.sub(mask_email, sanitized)

    # 6. Phone Numbers (including spaced formats like +91 98765 43210)
    sanitized = PHONE_REGEX.sub(mask_phone, sanitized)

    # 7. Remaining Bank Account Numbers
    sanitized = ACCOUNT_REGEX.sub(mask_account, sanitized)

    return sanitized


async def mask_sensitive_data_async(text: str) -> str:
    """Asynchronously sanitize text by offloading regex execution to a thread pool."""
    return await asyncio.to_thread(mask_sensitive_data, text)
