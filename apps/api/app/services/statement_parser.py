import csv
import io
import re
from datetime import UTC, datetime
from typing import Any

from app.services.categorizer import categorize_transaction
from app.services.data_sanitizer import mask_sensitive_data
from app.services.deduplication import compute_transaction_fingerprint


def _parse_date(date_str: str) -> datetime:
    """Attempt parsing multiple common date formats found in Indian bank statements."""
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%b-%Y",
        "%d %b %Y",
        "%d-%B-%Y",
        "%Y/%m/%d",
        "%d%b%y",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    # Default to current UTC time if date parsing fails
    return datetime.now(UTC)


def parse_csv_statement(content_str: str, account_id: str) -> list[dict[str, Any]]:
    """Parse a CSV bank statement with auto-detected columns."""
    reader = csv.reader(io.StringIO(content_str))
    rows = list(reader)
    if not rows:
        return []

    # Find header row
    header_idx = -1
    date_col = -1
    desc_col = -1
    debit_col = -1
    credit_col = -1
    amount_col = -1
    type_col = -1

    for idx, row in enumerate(rows[:10]):
        row_lower = [c.strip().lower() for c in row]
        for c_idx, col in enumerate(row_lower):
            if any(k in col for k in ["date", "txn date", "transaction date", "value date"]):
                date_col = c_idx
            elif any(k in col for k in ["narration", "description", "particulars", "remarks", "details"]):
                desc_col = c_idx
            elif any(k in col for k in ["debit", "withdrawal", "dr"]):
                debit_col = c_idx
            elif any(k in col for k in ["credit", "deposit", "cr"]):
                credit_col = c_idx
            elif "amount" in col:
                amount_col = c_idx
            elif "type" in col:
                type_col = c_idx

        if date_col != -1 and (desc_col != -1 or debit_col != -1 or credit_col != -1):
            header_idx = idx
            break

    # If no clear header was detected, default to standard column indices: 0: Date, 1: Description, 2: Debit, 3: Credit
    if header_idx == -1:
        header_idx = 0
        date_col = 0
        desc_col = 1
        debit_col = 2
        credit_col = 3

    parsed_transactions: list[dict[str, Any]] = []

    for row in rows[header_idx + 1:]:
        if not row or len(row) <= date_col:
            continue

        raw_date = row[date_col].strip()
        if not raw_date:
            continue
        parsed_date = _parse_date(raw_date)

        raw_desc = row[desc_col].strip() if desc_col < len(row) else "Bank Transaction"

        debit_val = 0.0
        credit_val = 0.0

        if debit_col != -1 and debit_col < len(row):
            clean_debit = re.sub(r'[^\d.]', '', row[debit_col])
            debit_val = float(clean_debit) if clean_debit else 0.0

        if credit_col != -1 and credit_col < len(row):
            clean_credit = re.sub(r'[^\d.]', '', row[credit_col])
            credit_val = float(clean_credit) if clean_credit else 0.0

        if debit_val == 0.0 and credit_val == 0.0 and amount_col != -1 and amount_col < len(row):
            clean_amt = re.sub(r'[^\d.]', '', row[amount_col])
            amt = float(clean_amt) if clean_amt else 0.0
            t_type = "debit"
            if (
                type_col != -1
                and type_col < len(row)
                and any(k in row[type_col].lower() for k in ["cr", "credit", "deposit"])
            ):
                t_type = "credit"
            if t_type == "credit":
                credit_val = amt
            else:
                debit_val = amt

        if debit_val > 0:
            amount = debit_val
            t_type = "debit"
        elif credit_val > 0:
            amount = credit_val
            t_type = "credit"
        else:
            continue

        category, merchant = categorize_transaction(raw_desc, t_type)
        masked_desc = mask_sensitive_data(raw_desc)
        fingerprint = compute_transaction_fingerprint(account_id, parsed_date, amount, t_type, raw_desc)

        parsed_transactions.append({
            "account_id": account_id,
            "date": parsed_date,
            "amount": amount,
            "transaction_type": t_type,
            "category": category,
            "description": raw_desc,
            "description_cleaned": masked_desc,
            "merchant": merchant,
            "fingerprint": fingerprint,
            "source": "csv_upload",
            "is_recurring": False,
        })

    return parsed_transactions


def parse_sms_statement(sms_text: str, account_id: str) -> dict[str, Any] | None:
    """Parse single Indian bank transaction alert SMS (HDFC, SBI, ICICI, Axis, Kotak, etc.)."""
    text = sms_text.strip()
    if not text:
        return None

    # Detect Amount
    amt_match = re.search(r'(?:rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)', text, re.IGNORECASE)
    if not amt_match:
        return None

    amt_str = amt_match.group(1).replace(",", "")
    amount = float(amt_str)

    # Detect transaction type (debit / credit)
    t_type = "debit"
    if re.search(r'\b(credited|received|deposited|refunded)\b', text, re.IGNORECASE):
        t_type = "credit"

    # Detect merchant / entity
    merchant_pattern = r'(?:at|to|info\/|by)\s+([A-Za-z0-9\s.\-_]+?)(?:\s+on|\s+ref|\.|\s+avail|\s+bal)'
    merchant_match = re.search(merchant_pattern, text, re.IGNORECASE)
    merchant_raw = merchant_match.group(1).strip() if merchant_match else ""

    category, merchant = categorize_transaction(merchant_raw or text, t_type)
    masked_text = mask_sensitive_data(text)
    tx_date = datetime.now(UTC)
    fingerprint = compute_transaction_fingerprint(account_id, tx_date, amount, t_type, text)

    return {
        "account_id": account_id,
        "date": tx_date,
        "amount": amount,
        "transaction_type": t_type,
        "category": category,
        "description": text,
        "description_cleaned": masked_text,
        "merchant": merchant or merchant_raw,
        "fingerprint": fingerprint,
        "source": "sms",
        "is_recurring": False,
    }
