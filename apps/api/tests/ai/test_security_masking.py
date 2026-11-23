import pytest

from app.ai.gateway.errors import MaskingFailed
from app.ai.security.leak_scanner import assert_no_leaks, scan_for_leaks
from app.ai.security.masking import is_luhn_valid, mask_pii


def test_luhn_validator():
    # Valid credit card numbers (test Visa / Mastercard test numbers)
    assert is_luhn_valid("4532015012345678") is False  # not valid checksum
    assert is_luhn_valid("4242424242424242") is True  # valid Luhn
    # Too short / too long
    assert is_luhn_valid("123456789") is False
    assert is_luhn_valid("123456789012345678901") is False


def test_phone_number_masking():
    texts = [
        ("Call me at +91-9876543210 please", "Call me at +91-XXXXX-X3210 please"),
        ("Phone: 9876543210 now", "Phone: +91-XXXXX-X3210 now"),
        ("Reach 09876543210", "Reach +91-XXXXX-X3210"),
    ]
    for raw, expected in texts:
        assert mask_pii(raw) == expected


def test_email_and_upi_masking():
    # Email
    assert mask_pii("Contact support@example.com for help") == "Contact s***t@example.com for help"
    # UPI IDs
    assert mask_pii("Send ₹500 to rahul@okhdfcbank via GPay") == "Send ₹500 to r***l@okhdfcbank via GPay"
    assert mask_pii("Pay to shop.pay@upi") == "Pay to s***y@upi"


def test_pan_and_aadhaar_masking():
    # PAN
    assert mask_pii("My PAN is ABCDE1234F.") == "My PAN is XXXXX1234X."
    # Aadhaar formatted
    assert mask_pii("Aadhaar: 1234 5678 9012") == "Aadhaar: XXXX-XXXX-9012"
    assert mask_pii("Aadhaar: 1234-5678-9012") == "Aadhaar: XXXX-XXXX-9012"


def test_bank_account_and_ifsc_masking():
    # Account in context
    assert mask_pii("Transfer to A/C: 123456789012") == "Transfer to A/C: ****9012"
    assert mask_pii("Credited to account no 987654321098") == "Credited to account no ****1098"
    # IFSC adjacent
    assert mask_pii("HDFC0001234, Account 123456789012") == "HDFC0001234, Account ****9012"


def test_otp_and_pin_masking():
    assert mask_pii("Your OTP is 4829 for txn") == "Your OTP is [MASKED_OTP] for txn"
    assert mask_pii("Use secret PIN: 9918") == "Use secret PIN: [MASKED_OTP]"


def test_financial_amounts_and_dates_preserved_unmasked():
    text = (
        "On 2026-11-21, ₹2,500.00 was debited. Balance is Rs. 18,400. "
        "Paid INR 450 yesterday. Total spent was 18400 on 21/11/2026."
    )
    masked = mask_pii(text)
    # Currency amounts must NEVER be masked!
    assert "₹2,500.00" in masked
    assert "Rs. 18,400" in masked
    assert "INR 450" in masked
    assert "18400" in masked
    # Dates must NEVER be masked!
    assert "2026-11-21" in masked
    assert "21/11/2026" in masked


def test_malayalam_and_manglish_pii_masking():
    # Malayalam
    malayalam_text = "എന്റെ ഫോൺ നമ്പർ 9876543210 ആണ്, ഒടിപി 5678 ആണ്. തുക ₹1,200."
    masked_mal = mask_pii(malayalam_text)
    assert "+91-XXXXX-X3210" in masked_mal
    assert "[MASKED_OTP]" in masked_mal
    assert "₹1,200" in masked_mal

    # Manglish
    manglish_text = "Ente phone 9876543210 aanu, upi id rahul@okhdfcbank aanu, balance ₹5,000 undu."
    masked_mang = mask_pii(manglish_text)
    assert "+91-XXXXX-X3210" in masked_mang
    assert "r***l@okhdfcbank" in masked_mang
    assert "₹5,000" in masked_mang


def test_known_names_masking():
    text = "Payment received from Rahul Sharma and Priya Nair."
    masked = mask_pii(text, known_names=["Rahul Sharma", "Priya Nair"])
    assert "Rahul Sharma" not in masked
    assert "Priya Nair" not in masked
    assert "[PERSON_NAME]" in masked


def test_leak_scanner_fails_closed():
    # High-risk unmasked PII triggers leak detection
    assert "unmasked_pan" in scan_for_leaks("Unmasked PAN: ABCDE1234F")
    assert "unmasked_phone_number" in scan_for_leaks("Call 9876543210")
    assert "unmasked_aadhaar" in scan_for_leaks("Aadhaar 1234 5678 9012")

    # Masked text has zero leaks
    safe_masked = "Call +91-XXXXX-X3210, PAN XXXXX1234X, spent ₹4,500 on 2026-11-21"
    assert scan_for_leaks(safe_masked) == []
    assert_no_leaks(safe_masked)

    # Fail closed on unmasked high-risk PII
    with pytest.raises(MaskingFailed):
        assert_no_leaks("Unmasked phone: 9876543210")
