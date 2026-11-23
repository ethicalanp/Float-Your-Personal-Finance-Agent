import unicodedata

from app.ai.rag.cleaner import clean_text
from app.ai.rag.language import detect_section_language


def test_clean_text_unicode_nfc_and_malayalam_preservation() -> None:
    # NFD text that should be normalized to NFC
    nfd_text = unicodedata.normalize("NFD", "Café and മലയാളം")
    cleaned = clean_text(nfd_text)

    assert unicodedata.is_normalized("NFC", cleaned)
    # Check Malayalam chillu characters and conjuncts are intact
    assert "മലയാളം" in cleaned


def test_clean_text_hyphenation_fix() -> None:
    broken = "Authorised push pay-\nments should have a cool-\ning period."
    cleaned = clean_text(broken)

    assert "Authorised push payments should have a cooling period." == cleaned


def test_clean_text_preserves_indic_zero_width_joiners() -> None:
    # Test Malayalam word with ZWJ and ZWNJ
    word_with_zwj = "അവൻ\u200d"  # chillu n with ZWJ
    cleaned = clean_text(word_with_zwj)
    assert "\u200d" in cleaned
    assert "അവൻ" in cleaned


def test_detect_section_language_malayalam() -> None:
    ml_text = "നിങ്ങളുടെ അക്കൗണ്ട് താൽക്കാലികമായി ബ്ലോക്ക് ചെയ്തിരിക്കുന്നു."
    lang, disagreement = detect_section_language(ml_text, manifest_language="ml")
    assert lang == "ml"
    assert disagreement is False


def test_detect_section_language_hindi() -> None:
    hi_text = "अपने बैंक खाते का विवरण किसी के साथ साझा न करें।"
    lang, disagreement = detect_section_language(hi_text, manifest_language="hi")
    assert lang == "hi"
    assert disagreement is False


def test_detect_section_language_manglish() -> None:
    manglish_text = "Udan thanne panam ayakkuka, linkil click cheyyu."
    lang, disagreement = detect_section_language(manglish_text, manifest_language="manglish")
    assert lang == "manglish"
    assert disagreement is False


def test_detect_section_language_reports_disagreement() -> None:
    # English text in a document that was flagged as Malayalam in manifest
    en_text = "This document contains standard banking regulations issued by the central bank."
    lang, disagreement = detect_section_language(en_text, manifest_language="ml")
    assert lang == "en"
    assert disagreement is True
