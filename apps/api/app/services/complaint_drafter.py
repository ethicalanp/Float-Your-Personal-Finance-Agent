from datetime import datetime, timezone
from typing import Any

from app.services.data_sanitizer import mask_sensitive_data
from app.services.verified_contacts import find_bank_contact, search_verified_contacts


def draft_fraud_complaint(
    victim_name: str,
    bank_name: str,
    account_number_mask: str,
    transaction_reference: str,
    transaction_amount: float,
    incident_date: str | None = None,
    scam_type: str = "Unauthorized Electronic Transaction / Fraud",
    description: str = "",
) -> dict[str, Any]:
    """Draft a formal grievance notice for the user to review and submit to their bank & cybercell."""
    bank_contact = find_bank_contact(bank_name)
    is_known_bank = bank_contact is not None

    if not bank_contact:
        bank_contact = {
            "institution": bank_name,
            "contact_type": "bank",
            "country_code": "IN",
            "toll_free_number": "[Refer to official bank passbook / card reverse]",
            "fraud_reporting_email": f"[Insert official grievance/fraud email for {bank_name}]",
            "website": f"[Official website of {bank_name}]",
            "is_verified": False,
            "notes": (
                f"Dedicated contact details for '{bank_name}' are not pre-indexed. "
                "Please obtain official nodal contacts directly from your bank's website."
            ),
        }

    # Fetch national cybercrime helpline details
    cyber_matches = search_verified_contacts("National Cyber Crime")
    cyber_portal = cyber_matches[0] if cyber_matches else {
        "institution": "National Cyber Crime Reporting Portal",
        "toll_free_number": "1930",
        "website": "https://cybercrime.gov.in",
    }

    date_formatted = incident_date or datetime.now(timezone.utc).strftime("%d-%B-%Y")
    masked_desc = mask_sensitive_data(description)

    # Formal Bank Email Draft
    bank_email_subject = (
        f"URGENT: Notice of Disputed / Unauthorized Electronic Transaction - "
        f"A/C {account_number_mask} - Ref: {transaction_reference}"
    )

    bank_email_body = f"""To,
The Nodal Grievance Officer / Fraud Monitoring Cell,
{bank_contact['institution']}

Subject: Formal Notice of Disputed Transaction under RBI Zero Liability Guidelines (Ref: {transaction_reference})

Respected Sir/Madam,

I am writing to report an unauthorized / fraudulent electronic transaction debiting my account:

Account Number (Masked): {account_number_mask}
Account Holder: {victim_name}
Transaction Date & Time: {date_formatted}
Disputed Amount: INR {transaction_amount:,.2f}
Transaction Reference / UTR No.: {transaction_reference}
Fraud Category: {scam_type}

Incident Chronology:
{masked_desc or "An unauthorized transaction occurred without my consent or authentication."}

In accordance with RBI guidelines on limiting customer liability in unauthorized electronic banking
transactions, I am submitting this formal notification promptly upon detection.

Requested Administrative Actions:
1. Promptly investigate the transaction and coordinate with the beneficiary institution to register a lien/dispute.
2. Formally register a chargeback or fraud dispute with the payment network / NPCI.
3. Review and secure compromised digital banking access credentials linked to this account.
4. Issue an official written Complaint / Grievance Reference Number acknowledging this report.

Yours sincerely,
{victim_name}
Date: {date_formatted}

[Disclaimer: Please verify the destination email address against your bank's official directory before sending.]
"""

    # National Cyber Crime 1930 / Portal Incident Log Template
    cyber_cell_template = f"""INCIDENT REPORT TEMPLATE FOR CYBERCRIME PORTAL (https://cybercrime.gov.in)
National Helpline: 1930

1. Complainant Name: {victim_name}
2. Bank / Financial Institution: {bank_contact['institution']}
3. Compromised Account Number (Masked): {account_number_mask}
4. Disputed Transaction Reference / UTR: {transaction_reference}
5. Amount Debited: INR {transaction_amount:,.2f}
6. Incident Date: {date_formatted}
7. Incident Type: Financial Cyber Fraud - {scam_type}
8. Summary:
{masked_desc}

Action Notice:
Calling the National Cybercrime Helpline at 1930 promptly after the transaction facilitates
registering the UTR on the CFCFRMS network for inter-bank tracking.
"""

    return {
        "is_known_bank": is_known_bank,
        "bank_contact": bank_contact,
        "cybercrime_helpline": cyber_portal,
        "bank_email_draft": {
            "to": bank_contact.get("fraud_reporting_email", ""),
            "subject": bank_email_subject,
            "body": bank_email_body,
        },
        "cyber_cell_draft": cyber_cell_template,
        "safety_disclaimer": (
            "This complaint draft is an informational tool prepared for your review and submission. "
            "Float does not file complaints, contact banks, or initiate account freezes on your behalf."
        ),
        "recommended_first_hour_checklist": [
            (
                f"Contact {bank_contact['institution']} support ({bank_contact.get('toll_free_number')}) "
                "to block cards/netbanking access."
            ),
            "Dial National Cyber Crime Helpline 1930 immediately to submit the UTR for inter-bank tracking.",
            "Verify your bank's official grievance email and send this formal written dispute notice.",
            "Reset passwords and UPI MPINs across all personal banking applications.",
        ],
    }
