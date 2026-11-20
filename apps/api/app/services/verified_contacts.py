from typing import Any

VERIFIED_DIRECTORY: list[dict[str, Any]] = [
    {
        "institution": "National Cyber Crime Reporting Portal",
        "contact_type": "government",
        "country_code": "IN",
        "toll_free_number": "1930",
        "fraud_reporting_email": "complaint-mgr@cybercrime.gov.in",
        "website": "https://cybercrime.gov.in",
        "source_url": "https://cybercrime.gov.in/Webform/Helpline.aspx",
        "last_verified_at": "2026-01-15",
        "is_verified": True,
        "notes": (
            "Citizen Financial Cyber Fraud Reporting System. Contacting 1930 promptly "
            "facilitates coordinated alerts to intermediary payment aggregators."
        ),
    },
    {
        "institution": "State Bank of India (SBI)",
        "contact_type": "bank",
        "country_code": "IN",
        "toll_free_number": "1800 1234 / 1800 2100",
        "fraud_reporting_email": "report.phishing@sbi.co.in",
        "website": "https://bank.sbi",
        "sms_block_code": "SMS 'BLOCK <last 4 digits>' to 567676",
        "source_url": "https://bank.sbi/web/customer-care/cyber-security",
        "last_verified_at": "2026-01-10",
        "is_verified": True,
        "notes": "Official SBI customer care fraud helpline.",
    },
    {
        "institution": "HDFC Bank",
        "contact_type": "bank",
        "country_code": "IN",
        "toll_free_number": "1800 1600 / 1800 2600",
        "fraud_reporting_email": "report.phishing@hdfcbank.com",
        "website": "https://www.hdfcbank.com",
        "sms_block_code": "SMS 'BLOCK <card last 4>' to 5676712",
        "source_url": "https://www.hdfcbank.com/personal/useful-links/security",
        "last_verified_at": "2026-01-10",
        "is_verified": True,
        "notes": "HDFC Bank 24/7 dedicated fraud reporting desk.",
    },
    {
        "institution": "ICICI Bank",
        "contact_type": "bank",
        "country_code": "IN",
        "toll_free_number": "1800 1080",
        "fraud_reporting_email": "antiphishing@icicibank.com",
        "website": "https://www.icicibank.com",
        "sms_block_code": "SMS 'BLOCK <last 4 digits>' to 5676766",
        "source_url": "https://www.icicibank.com/safe-banking",
        "last_verified_at": "2026-01-10",
        "is_verified": True,
        "notes": "ICICI Bank anti-phishing cell.",
    },
    {
        "institution": "Axis Bank",
        "contact_type": "bank",
        "country_code": "IN",
        "toll_free_number": "1860 419 5555 / 1860 500 5555",
        "fraud_reporting_email": "suspicious.email@axisbank.com",
        "website": "https://www.axisbank.com",
        "sms_block_code": "SMS 'BLOCKCARD' to 5676782",
        "source_url": "https://www.axisbank.com/support/report-suspicious-activity",
        "last_verified_at": "2026-01-10",
        "is_verified": True,
        "notes": "Axis Bank emergency emergency assistance.",
    },
    {
        "institution": "Kotak Mahindra Bank",
        "contact_type": "bank",
        "country_code": "IN",
        "toll_free_number": "1860 266 2666",
        "fraud_reporting_email": "phishing@kotak.com",
        "website": "https://www.kotak.com",
        "sms_block_code": "SMS 'DCBLOCK <last 4 digits>' to 9971056767",
        "source_url": "https://www.kotak.com/en/fraud-awareness.html",
        "last_verified_at": "2026-01-10",
        "is_verified": True,
        "notes": "Kotak Bank dedicated security center.",
    },
    {
        "institution": "Punjab National Bank (PNB)",
        "contact_type": "bank",
        "country_code": "IN",
        "toll_free_number": "1800 180 2222 / 1800 103 2222",
        "fraud_reporting_email": "care@pnb.co.in",
        "website": "https://pnbindia.in",
        "sms_block_code": "SMS 'HOT <Card No>' to 5607040",
        "source_url": "https://pnbindia.in/cyber-security.html",
        "last_verified_at": "2026-01-10",
        "is_verified": True,
        "notes": "PNB customer care helpline.",
    },
]


def get_all_verified_contacts() -> list[dict[str, Any]]:
    """Return the complete directory of financial helplines and cyber cells."""
    return VERIFIED_DIRECTORY


def find_bank_contact(bank_name: str) -> dict[str, Any] | None:
    """Find a specific bank in the directory, strictly returning bank entities (not law enforcement)."""
    if not bank_name:
        return None
    name_lower = bank_name.strip().lower()
    for entry in VERIFIED_DIRECTORY:
        if entry["contact_type"] == "bank" and (
            name_lower in entry["institution"].lower()
            or entry["institution"].lower() in name_lower
        ):
            return entry
    return None


def search_verified_contacts(query: str) -> list[dict[str, Any]]:
    """Filter contacts by institution name or keyword. Returns empty list if no match found."""
    if not query or not query.strip():
        return VERIFIED_DIRECTORY

    q_lower = query.strip().lower()
    matches = [
        entry for entry in VERIFIED_DIRECTORY
        if q_lower in entry["institution"].lower() or q_lower in entry["contact_type"].lower()
    ]
    return matches
