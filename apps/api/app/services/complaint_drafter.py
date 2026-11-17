from datetime import datetime, timezone
from typing import Any

from app.services.data_sanitizer import mask_sensitive_data
from app.services.verified_contacts import search_verified_contacts


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
    """Draft a formal, structured grievance notice for the user to submit to their bank & cybercell."""
    contacts = search_verified_contacts(bank_name)
    bank_contact = contacts[0] if contacts else {
        "institution": bank_name,
        "toll_free_number": "Contact official branch",
        "fraud_reporting_email": "Official bank nodal email",
        "website": "Bank portal",
    }

    cyber_portal = search_verified_contacts("National Cyber Crime")[0]
    date_formatted = incident_date or datetime.now(timezone.utc).strftime("%d-%B-%Y")
    masked_desc = mask_sensitive_data(description)

    # Formal Bank Email Draft
    bank_email_subject = f"URGENT: Dispute of Unauthorized Fraud Transaction - A/C {account_number_mask} - Ref: {transaction_reference}"
    bank_email_body = f"""To,
The Nodal Grievance Officer / Fraud Monitoring Cell,
{bank_contact['institution']}

Subject: Formal Notice of Unauthorized Transaction under RBI Zero Liability Guidelines (Ref: {transaction_reference})

Respected Sir/Madam,

I am writing to immediately report an unauthorized fraudulent transaction debiting my account:

Account Number: {account_number_mask}
Account Holder: {victim_name}
Transaction Date & Time: {date_formatted}
Disputed Amount: INR {transaction_amount:,.2f}
Transaction Reference / UTR No.: {transaction_reference}
Fraud Nature: {scam_type}

Incident Summary:
{masked_desc or "An unauthorized transaction occurred without my consent or authorization."}

In accordance with Reserve Bank of India (RBI) Circular RBI/2017-18/15 (Limiting Liability of Customers in Unauthorized Electronic Banking Transactions), I am reporting this incident within the immediate reporting window.

Requested Actions:
1. Immediately place a lien/freeze on the recipient account/beneficiary wallet to recover the funds.
2. Register a formal chargeback / fraud dispute with the nodal payment gateway/NPCI.
3. Block any compromised digital banking channels linked to this account.
4. Acknowledge this grievance in writing with an official Complaint/Ticket Reference Number.

Yours sincerely,
{victim_name}
Date: {date_formatted}
"""

    # National Cyber Crime 1930 / Portal Complaint Template
    cyber_cell_template = f"""INCIDENT REPORT FOR CYBERCRIME PORTAL (https://cybercrime.gov.in / Helpline: 1930)

1. Complainant Name: {victim_name}
2. Bank / Institution: {bank_contact['institution']}
3. Compromised Account: {account_number_mask}
4. Disputed Transaction Ref / UTR: {transaction_reference}
5. Amount Debited: INR {transaction_amount:,.2f}
6. Incident Date: {date_formatted}
7. Category: Financial Fraud - {scam_type}
8. Brief Chronology:
{masked_desc}

Note: Calling National Cybercrime Helpline 1930 immediately with this UTR reference enables the police cybercell to halt fund transfers across intermediary bank nodes.
"""

    return {
        "verified_bank_contact": bank_contact,
        "verified_cybercrime_helpline": cyber_portal,
        "bank_email_draft": {
            "to": bank_contact.get("fraud_reporting_email", ""),
            "subject": bank_email_subject,
            "body": bank_email_body,
        },
        "cyber_cell_draft": cyber_cell_template,
        "safety_disclaimer": "This draft is provided for your review and submission. Float will never submit legal complaints or freeze accounts autonomously.",
        "recommended_first_hour_checklist": [
            f"Call {bank_contact['institution']} helpline at {bank_contact['toll_free_number']} to lock cards and netbanking.",
            "Dial National Cyber Crime Helpline 1930 immediately to register the UTR number in the national fraud tracking portal.",
            "Send the above drafted notice to your bank's official grievance email to establish your timestamp under RBI zero liability rules.",
            "Change passwords and MPINs on all banking applications.",
        ],
    }
