from app.ai.gateway.errors import MaskingFailed
from app.ai.security.masking import (
    AADHAAR_REGEX,
    CARD_CANDIDATE_REGEX,
    PAN_REGEX,
    PHONE_REGEX,
    is_luhn_valid,
)


def scan_for_leaks(text: str) -> list[str]:
    """Scan text for any remaining unmasked high-risk PII patterns.

    Returns a list of detected leak categories.
    """
    if not text:
        return []

    leaks: list[str] = []

    # 1. Check for unmasked card numbers (Luhn-valid, 13-19 digits, not containing mask chars)
    for match in CARD_CANDIDATE_REGEX.finditer(text):
        matched_str = match.group(0)
        if "*" not in matched_str and "X" not in matched_str:
            digits_only = "".join(c for c in matched_str if c.isdigit())
            if is_luhn_valid(digits_only):
                leaks.append("unmasked_card_number")
                break

    # 2. Check for unmasked Aadhaar (12 digits, spaced or continuous, no mask chars)
    for match in AADHAAR_REGEX.finditer(text):
        matched_str = match.group(0)
        if "X" not in matched_str and "*" not in matched_str:
            leaks.append("unmasked_aadhaar")
            break

    # 3. Check for unmasked PAN (5 letters, 4 digits, 1 letter, no mask chars)
    for match in PAN_REGEX.finditer(text):
        matched_str = match.group(0)
        if "X" not in matched_str and "*" not in matched_str:
            leaks.append("unmasked_pan")
            break

    # 4. Check for unmasked Phone numbers (10 digits starting with 6-9, no mask chars)
    for match in PHONE_REGEX.finditer(text):
        matched_str = match.group(0)
        if "X" not in matched_str and "*" not in matched_str:
            leaks.append("unmasked_phone_number")
            break

    return leaks


def assert_no_leaks(text: str) -> None:
    """Fail closed: raise MaskingFailed if any unmasked high-risk PII is found."""
    leaks = scan_for_leaks(text)
    if leaks:
        raise MaskingFailed(f"Post-mask leak scanner detected unmasked high-risk PII: {', '.join(leaks)}")
