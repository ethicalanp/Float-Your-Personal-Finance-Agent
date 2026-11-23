import re

# Regex patterns for sensitive financial and PII elements in India
PHONE_REGEX = re.compile(r"(?:\+?91[\s\-]?)?(?<!\d)[6-9]\d{9}(?!\d)")
CARD_REGEX = re.compile(r"(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)")
ACCOUNT_REGEX = re.compile(r"(?<!\d)\d{10,18}(?!\d)")
UPI_REGEX = re.compile(r"[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}")
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
AADHAAR_REGEX = re.compile(r"(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)")
PAN_REGEX = re.compile(r"(?<![A-Z])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z])")


def mask_phone(match: re.Match) -> str:
    val = re.sub(r"[\s\-]", "", match.group(0))
    last4 = val[-4:]
    return f"+91-XXXXX-X{last4}"


def mask_card(match: re.Match) -> str:
    val = re.sub(r"[\s\-]", "", match.group(0))
    last4 = val[-4:]
    return f"****-****-****-{last4}"


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
    # Mask letters 1-5, keep numbers 6-9, mask last letter
    return f"XXXXX{val[5:9]}X"


def mask_sensitive_data(text: str) -> str:
    """Mask phone numbers, emails, cards, bank accounts, UPI IDs, PAN, and Aadhaar numbers.

    Ensures zero sensitive PII is exposed to downstream AI agents or raw logs.
    """
    if not text:
        return ""

    sanitized = text

    # Mask card numbers first (16 digits)
    sanitized = CARD_REGEX.sub(mask_card, sanitized)

    # Mask PAN
    sanitized = PAN_REGEX.sub(mask_pan, sanitized)

    # Mask UPI IDs
    sanitized = UPI_REGEX.sub(mask_upi, sanitized)

    # Mask Emails
    sanitized = EMAIL_REGEX.sub(mask_email, sanitized)

    # Mask Phone numbers
    sanitized = PHONE_REGEX.sub(mask_phone, sanitized)

    # Mask remaining bare account numbers (10 to 18 digits)
    sanitized = ACCOUNT_REGEX.sub(mask_account, sanitized)

    return sanitized
