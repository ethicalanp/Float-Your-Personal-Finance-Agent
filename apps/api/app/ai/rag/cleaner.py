import re
import unicodedata


def clean_text(text: str) -> str:
    """Clean and normalize document text while strictly preserving Malayalam and Indic scripts.

    - Normalizes Unicode to NFC form.
    - Fixes hyphenated line breaks (e.g. 'compen-\\nsation' -> 'compensation').
    - Removes non-printable ASCII control characters.
    - Preserves Malayalam characters (0x0D00-0x0D7F), Zero Width Joiner (\\u200D), and Zero Width Non-Joiner (\\u200C).
    - Normalizes excessive whitespace and repeated blank lines.
    """
    if not text:
        return ""

    # 1. Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", text)

    # 2. Fix broken hyphenation at line breaks (word-\nword -> wordword)
    # Only join if preceding character and succeeding character are alphabetic
    normalized = re.sub(r"([a-zA-Z\u0D00-\u0D7F])-\s*\n\s*([a-zA-Z\u0D00-\u0D7F])", r"\1\2", normalized)

    # 3. Clean control characters while preserving newline, tab, and Indic joiners
    cleaned_chars = []
    for c in normalized:
        code = ord(c)
        if c in "\n\r\t":
            cleaned_chars.append(c)
        elif code in (0x200C, 0x200D):  # ZWNJ and ZWJ essential for Malayalam chillu & conjuncts
            cleaned_chars.append(c)
        elif 0x00 <= code < 0x20 or code == 0x7F:
            # Drop unprintable ASCII controls
            continue
        else:
            cleaned_chars.append(c)

    text_filtered = "".join(cleaned_chars)

    # 4. Normalize spaces and excessive blank lines
    # Replace multiple horizontal spaces with a single space
    text_filtered = re.sub(r"[ \t]+", " ", text_filtered)
    # Collapse 3+ consecutive newlines into 2
    text_filtered = re.sub(r"\n{3,}", "\n\n", text_filtered)

    return text_filtered.strip()
