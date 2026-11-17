from typing import Any

VERIFIED_DIRECTORY: list[dict[str, Any]] = [
    {
        "institution": "National Cyber Crime Reporting Portal",
        "category": "Government & Law Enforcement",
        "toll_free_number": "1930",
        "alternate_number": "112",
        "website": "https://cybercrime.gov.in",
        "reporting_channel": "Citizen Financial Cyber Fraud Reporting and Management System (CFCFRMS)",
        "priority_notice": "Call 1930 within the golden first hour to trigger immediate inter-bank freeze of stolen funds.",
    },
    {
        "institution": "State Bank of India (SBI)",
        "category": "Public Sector Bank",
        "toll_free_number": "1800 1234 / 1800 2100",
        "fraud_reporting_email": "report.phishing@sbi.co.in",
        "website": "https://bank.sbi",
        "sms_block_code": "SMS 'BLOCK <last 4 digits of card>' to 567676",
        "priority_notice": "Call customer support to block netbanking & debit cards immediately.",
    },
    {
        "institution": "HDFC Bank",
        "category": "Private Sector Bank",
        "toll_free_number": "1800 1600 / 1800 2600",
        "fraud_reporting_email": "report.phishing@hdfcbank.com",
        "website": "https://www.hdfcbank.com",
        "sms_block_code": "SMS 'BLOCK <card last 4>' to 5676712",
        "priority_notice": "Use MobileBanking App > Cards > Block Card for instant block.",
    },
    {
        "institution": "ICICI Bank",
        "category": "Private Sector Bank",
        "toll_free_number": "1800 1080",
        "fraud_reporting_email": "antiphishing@icicibank.com",
        "website": "https://www.icicibank.com",
        "sms_block_code": "SMS 'BLOCK <last 4 digits>' to 5676766",
        "priority_notice": "Lock NetBanking ID via iMobile App instantly under security settings.",
    },
    {
        "institution": "Axis Bank",
        "category": "Private Sector Bank",
        "toll_free_number": "1860 419 5555 / 1860 500 5555",
        "fraud_reporting_email": "suspicious.email@axisbank.com",
        "website": "https://www.axisbank.com",
        "sms_block_code": "SMS 'BLOCKCARD' to 5676782",
        "priority_notice": "Open Axis Mobile App > Services > Debit Card > Block.",
    },
    {
        "institution": "Kotak Mahindra Bank",
        "category": "Private Sector Bank",
        "toll_free_number": "1860 266 2666",
        "fraud_reporting_email": "phishing@kotak.com",
        "website": "https://www.kotak.com",
        "sms_block_code": "SMS 'DCBLOCK <last 4 digits>' to 9971056767",
        "priority_notice": "Block card instantly via Kotak 811 App under Card Control.",
    },
    {
        "institution": "Punjab National Bank (PNB)",
        "category": "Public Sector Bank",
        "toll_free_number": "1800 180 2222 / 1800 103 2222",
        "fraud_reporting_email": "care@pnb.co.in",
        "website": "https://pnbindia.in",
        "sms_block_code": "SMS 'HOT <Card No>' to 5607040",
        "priority_notice": "Contact customer care hotline immediately to block account access.",
    },
]


def get_all_verified_contacts() -> list[dict[str, Any]]:
    """Return the complete verified directory of financial helplines and cyber cells."""
    return VERIFIED_DIRECTORY


def search_verified_contacts(query: str) -> list[dict[str, Any]]:
    """Filter verified contacts by bank name, category, or keyword."""
    if not query or not query.strip():
        return VERIFIED_DIRECTORY

    q_lower = query.strip().lower()
    results = []
    for entry in VERIFIED_DIRECTORY:
        inst = entry["institution"].lower()
        cat = entry["category"].lower()
        if q_lower in inst or q_lower in cat:
            results.append(entry)
    return results or VERIFIED_DIRECTORY
