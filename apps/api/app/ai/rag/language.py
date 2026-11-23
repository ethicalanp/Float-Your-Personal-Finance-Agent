import re

MANGLISH_MARKERS = {
    "cheyyuka",
    "cheyyu",
    "cheyyanam",
    "panam",
    "linkil",
    "aakum",
    "thanne",
    "vannal",
    "enthu",
    "kodukkuka",
    "koduthu",
    "varum",
    "illa",
    "nokku",
    "parathi",
    "thattippu",
    "udane",
    "ningalude",
    "swantham",
    "adakkillel",
}


def detect_section_language(
    text: str,
    manifest_language: str = "en",
) -> tuple[str, bool]:
    """Detect section language based on Unicode script ranges and Manglish tokens.

    Returns:
        (detected_language, has_disagreement_with_manifest)
    """
    if not text.strip():
        return manifest_language, False

    ml_count = 0
    hi_count = 0
    latin_count = 0

    for ch in text:
        code = ord(ch)
        if 0x0D00 <= code <= 0x0D7F:
            ml_count += 1
        elif 0x0900 <= code <= 0x097F:
            hi_count += 1
        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            latin_count += 1

    total_alpha = ml_count + hi_count + latin_count
    if total_alpha == 0:
        return manifest_language, False

    ml_ratio = ml_count / total_alpha
    hi_ratio = hi_count / total_alpha

    detected: str
    if ml_ratio >= 0.15:
        detected = "ml"
    elif hi_ratio >= 0.15:
        detected = "hi"
    else:
        # Script is Latin
        if manifest_language == "manglish":
            detected = "manglish"
        else:
            # Check for explicit Manglish phonetic markers
            tokens = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))
            overlap = tokens.intersection(MANGLISH_MARKERS)
            if len(overlap) >= 2 or (len(overlap) >= 1 and len(tokens) <= 10):
                detected = "manglish"
            else:
                detected = "en"

    has_disagreement = False
    if manifest_language not in ("mixed", "und"):
        if detected != manifest_language:
            has_disagreement = True

    return detected, has_disagreement
