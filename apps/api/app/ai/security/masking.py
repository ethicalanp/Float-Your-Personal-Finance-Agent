import re

# Pre-compiled regex patterns for Indian financial identifiers and PII

# Email and UPI IDs
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
UPI_REGEX = re.compile(r"\b[a-zA-Z0-9.\-_]{2,}@(?!gmail|yahoo|hotmail|outlook|icloud|proton)[a-zA-Z]{2,}\b")

# Indian PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_REGEX = re.compile(r"\b([A-Z]{5})(\d{4})([A-Z])\b")

# Indian Aadhaar: 12 digits, often in 4-4-4 format with space or hyphen
AADHAAR_REGEX = re.compile(r"\b(\d{4})[\s\-](\d{4})[\s\-](\d{4})\b")

# Indian Mobile numbers: starts with 6, 7, 8, 9, 10 digits; optionally prefixed with +91 or 0
PHONE_REGEX = re.compile(r"(?<!\d)(?<![₹$€£¥])(?<![0-9.,])(?:\+91[\s\-]?|91[\s\-]?|0)?([6-9]\d{9})(?!\d)(?![.,]\d)")

# IFSC Code: 4 letters, 0, 6 alphanumeric characters
IFSC_REGEX = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")

# Account numbers adjacent to keywords or IFSC (9 to 18 digits)
ACCOUNT_CONTEXT_REGEX = re.compile(
    r"(?i)\b(?:a/?c|acct|account(?:\s*no(?:\.|\b)?)?|acc(?:\s*no(?:\.|\b)?)?|a/c\s*no|ಖಾತೆ|അക്കൗണ്ട്|खाता)\s*[:#-]?\s*(\d{9,18})\b"
)
IFSC_ADJACENT_REGEX = re.compile(
    r"(\b[A-Z]{4}0[A-Z0-9]{6}\b)[\s,:\-]+(?:a/?c|account)?[\s,:\-]*(\d{9,18})",
    re.IGNORECASE,
)

# OTP / PIN when stated in text (in English, Malayalam, Manglish)
OTP_REGEX = re.compile(
    r"(?i)\b(?:otp|one\s*time\s*password|pin|passcode|രഹസ്യകോഡ്|പിൻ|ഒടിപി)\s*(?:is|code|:|=|—|-)?\s*(\d{4,8})\b"
)

# General card number candidate (13 to 19 digits with optional spaces or hyphens)
CARD_CANDIDATE_REGEX = re.compile(r"(?<!\d)(?:\d{4}[\s\-]?){3}\d{1,7}(?!\d)")


def is_luhn_valid(number_str: str) -> bool:
    """Validate a card number string using Luhn's algorithm (mod 10)."""
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False

    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def mask_luhn_card(match: re.Match[str]) -> str:
    raw = match.group(0)
    digits_only = re.sub(r"[\s\-]", "", raw)
    if is_luhn_valid(digits_only):
        last4 = digits_only[-4:]
        return f"****-****-****-{last4}"
    return raw


def mask_phone_match(match: re.Match[str]) -> str:
    ten_digit = match.group(1)
    last4 = ten_digit[-4:]
    return f"+91-XXXXX-X{last4}"


def mask_email_match(match: re.Match[str]) -> str:
    raw = match.group(0)
    user_part, domain = raw.split("@", 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + "*"
    else:
        masked_user = user_part[0] + "***" + user_part[-1]
    return f"{masked_user}@{domain}"


def mask_upi_match(match: re.Match[str]) -> str:
    raw = match.group(0)
    user_part, handle_bank = raw.split("@", 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + "*"
    else:
        masked_user = user_part[0] + "***" + user_part[-1]
    return f"{masked_user}@{handle_bank}"


def mask_pan_match(match: re.Match[str]) -> str:
    digits = match.group(2)
    return f"XXXXX{digits}X"


def mask_aadhaar_match(match: re.Match[str]) -> str:
    last4 = match.group(3)
    return f"XXXX-XXXX-{last4}"


def mask_account_context_match(match: re.Match[str]) -> str:
    full = match.group(0)
    acc = match.group(1)
    last4 = acc[-4:]
    return full.replace(acc, f"****{last4}")


def mask_otp_match(match: re.Match[str]) -> str:
    full = match.group(0)
    code = match.group(1)
    return full.replace(code, "[MASKED_OTP]")


def mask_pii(text: str, known_names: list[str] | None = None) -> str:
    """Mask sensitive PII in text while strictly preserving financial amounts and dates.

    Preserves:
    - Currency amounts: e.g. ₹2,500.00, Rs. 18,400, INR 450, 18400.
    - Dates: e.g. 2026-11-21, 21/11/2026, yesterday, Oct 21.

    Masks:
    - Credit/Debit cards (Luhn valid) -> ****-****-****-1234
    - PAN -> XXXXX1234X
    - Aadhaar (12-digit formatted) -> XXXX-XXXX-1234
    - UPI IDs -> u***r@okhdfcbank
    - Email addresses -> u***r@example.com
    - Mobile numbers -> +91-XXXXX-X1234
    - Bank Account numbers in account context or IFSC adjacent -> ****1234
    - OTPs/PINs in text -> [MASKED_OTP]
    - Known full names -> [PERSON_NAME]
    """
    if not text:
        return ""

    sanitized = text

    # 1. Mask Credit / Debit cards (Luhn validated so amounts are never touched)
    sanitized = CARD_CANDIDATE_REGEX.sub(mask_luhn_card, sanitized)

    # 2. Mask Aadhaar numbers (12-digit spaced/hyphenated)
    sanitized = AADHAAR_REGEX.sub(mask_aadhaar_match, sanitized)

    # 3. Mask PAN numbers
    sanitized = PAN_REGEX.sub(mask_pan_match, sanitized)

    # 4. Mask Email addresses
    sanitized = EMAIL_REGEX.sub(mask_email_match, sanitized)

    # 5. Mask UPI IDs
    sanitized = UPI_REGEX.sub(mask_upi_match, sanitized)

    # 6. Mask IFSC-adjacent bank accounts
    def _mask_ifsc_adjacent(m: re.Match[str]) -> str:
        acc = m.group(2)
        return m.group(0).replace(acc, f"****{acc[-4:]}")

    sanitized = IFSC_ADJACENT_REGEX.sub(_mask_ifsc_adjacent, sanitized)

    # 7. Mask Bank Accounts with explicit account context
    sanitized = ACCOUNT_CONTEXT_REGEX.sub(mask_account_context_match, sanitized)

    # 8. Mask OTPs / PINs in text
    sanitized = OTP_REGEX.sub(mask_otp_match, sanitized)

    # 9. Mask Indian Mobile numbers
    sanitized = PHONE_REGEX.sub(mask_phone_match, sanitized)

    # 10. Mask known full names if provided
    if known_names:
        for name in known_names:
            clean_name = name.strip()
            if clean_name and len(clean_name) >= 3:
                name_pattern = re.compile(rf"\b{re.escape(clean_name)}\b", re.IGNORECASE)
                sanitized = name_pattern.sub("[PERSON_NAME]", sanitized)

    return sanitized
