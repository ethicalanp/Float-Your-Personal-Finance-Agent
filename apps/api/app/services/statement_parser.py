import csv
import io
import re
import time
import zlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.services.categorizer import categorize_transaction
from app.services.data_sanitizer import mask_sensitive_data
from app.services.deduplication import compute_transaction_fingerprint

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 60_000
CSV_PARSE_TIMEOUT_SECONDS = 30.0
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def escape_csv_formula(value: str) -> str:
    """Prefix spreadsheet formula triggers (=, +, -, @, tab, cr) with a single quote."""
    if value and value.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %b %Y",
    "%d %b %y",
    "%d-%B-%Y",
    "%Y/%m/%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d%b%y",
)

AMOUNT_CLEAN_RE = re.compile(r"[^\d.\-]")
PDF_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
PDF_TEXT_OP_RE = re.compile(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj|\[(.*?)\]\s*TJ", re.DOTALL)
PDF_TJ_STR_RE = re.compile(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)")


class StatementParseError(ValueError):
    """User-facing parse error with row-level or file-level diagnostics."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors[:5]))


@dataclass
class StatementParseResult:
    transactions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    balance_warnings: list[str] = field(default_factory=list)


def decode_statement_bytes(raw: bytes) -> str:
    """Decode statement bytes supporting UTF-8 BOM, UTF-8, and Windows-1252."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _try_parse_date(date_str: str, preferred_fmt: str | None = None) -> tuple[datetime | None, str | None]:
    s = date_str.strip()
    if not s:
        return None, preferred_fmt
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day, tzinfo=UTC), "%Y-%m-%d"
        except ValueError:
            pass
    if preferred_fmt is not None:
        try:
            return datetime.strptime(s, preferred_fmt).replace(tzinfo=UTC), preferred_fmt
        except ValueError:
            pass
    for fmt in DATE_FORMATS:
        if fmt == preferred_fmt:
            continue
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC), fmt
        except ValueError:
            continue
    return None, preferred_fmt


def _parse_date(date_str: str) -> datetime:
    """Attempt parsing multiple common date formats found in Indian bank statements."""
    parsed, _ = _try_parse_date(date_str)
    if parsed is not None:
        return parsed
    return datetime.now(UTC)


def _parse_amount(raw: str) -> tuple[float, str | None, bool]:
    """Parse Indian lakh-formatted, signed, or Dr/Cr-suffixed amount strings.

    Returns (abs_amount, inferred_type_or_none, is_valid).
    """
    s = raw.strip()
    if not s:
        return 0.0, None, True
    # Fast path for plain positive numbers / comma-formatted numbers
    if s[0].isdigit() and s[-1].isdigit() and " " not in s:
        try:
            return float(s.replace(",", "")), None, True
        except ValueError:
            pass
    lower = s.lower()
    inferred_type: str | None = None
    if re.search(r"\bdr\b|\bdebit\b", lower):
        inferred_type = "debit"
    elif re.search(r"\bcr\b|\bcredit\b", lower):
        inferred_type = "credit"

    is_negative = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    cleaned = AMOUNT_CLEAN_RE.sub("", s.replace(",", ""))
    if not cleaned or cleaned in ("-", "."):
        return 0.0, inferred_type, False
    try:
        val = float(cleaned)
    except ValueError:
        return 0.0, inferred_type, False

    if val < 0 or is_negative:
        val = abs(val)
        if inferred_type is None:
            inferred_type = "debit"
    return val, inferred_type, True


def _detect_delimiter(sample_lines: list[str]) -> str:
    for delim in (";", ",", "\t"):
        if any(line.count(delim) >= 2 for line in sample_lines[:15]):
            if delim == ";" and any(line.count(";") >= line.count(",") for line in sample_lines[:15]):
                return ";"
            if delim == "," and any(line.count(",") >= 2 for line in sample_lines[:15]):
                return ","
            if delim == "\t":
                return "\t"
    return ","


def parse_csv_statement_with_diagnostics(
    content: str | bytes,
    account_id: str,
    raise_on_row_error: bool = False,
    max_bytes: int = MAX_CSV_BYTES,
    max_rows: int = MAX_CSV_ROWS,
    timeout_seconds: float = CSV_PARSE_TIMEOUT_SECONDS,
) -> StatementParseResult:
    """Parse CSV/semicolon bank statements with size/row/timeout caps, shifted headers, and balance validation."""
    raw_bytes = content if isinstance(content, bytes) else content.encode("utf-8", errors="replace")
    if len(raw_bytes) > max_bytes:
        raise StatementParseError([f"CSV size ({len(raw_bytes)} bytes) exceeds maximum allowed {max_bytes} bytes."])

    parse_start = time.monotonic()
    content_str = decode_statement_bytes(content) if isinstance(content, bytes) else content
    content_str = content_str.lstrip("\ufeff").strip()
    if not content_str:
        return StatementParseResult()

    sample_lines = content_str.splitlines()[:25]
    delimiter = _detect_delimiter(sample_lines)
    rows = list(csv.reader(io.StringIO(content_str), delimiter=delimiter))
    if not rows:
        return StatementParseResult()
    if len(rows) > max_rows:
        raise StatementParseError([f"CSV row count ({len(rows)}) exceeds maximum allowed {max_rows} rows."])

    header_idx = -1
    date_col = -1
    desc_col = -1
    debit_col = -1
    credit_col = -1
    amount_col = -1
    type_col = -1
    balance_col = -1

    for idx, row in enumerate(rows[:30]):
        row_lower = [c.strip().lower() for c in row]
        d_c = desc_c = dr_c = cr_c = amt_c = typ_c = bal_c = -1
        for c_idx, col in enumerate(row_lower):
            if any(k in col for k in ("date", "txn date", "transaction date", "value date")):
                d_c = c_idx
            elif any(k in col for k in ("narration", "description", "particulars", "remarks", "details")):
                desc_c = c_idx
            elif any(k in col for k in ("debit", "withdrawal", "dr")):
                dr_c = c_idx
            elif any(k in col for k in ("credit", "deposit", "cr")):
                cr_c = c_idx
            elif "amount" in col:
                amt_c = c_idx
            elif "type" in col:
                typ_c = c_idx
            elif "balance" in col:
                bal_c = c_idx

        if d_c != -1 and (desc_c != -1 or dr_c != -1 or cr_c != -1 or amt_c != -1):
            header_idx = idx
            date_col, desc_col, debit_col, credit_col, amount_col, type_col, balance_col = (
                d_c,
                desc_c,
                dr_c,
                cr_c,
                amt_c,
                typ_c,
                bal_c,
            )
            break

    if header_idx == -1:
        header_idx = 0
        date_col, desc_col, debit_col, credit_col = 0, 1, 2, 3

    parsed_transactions: list[dict[str, Any]] = []
    errors: list[str] = []
    balance_warnings: list[str] = []
    prev_balance: float | None = None
    preferred_date_fmt: str | None = None
    cat_cache: dict[tuple[str, str], tuple[str, str | None]] = {}
    mask_cache: dict[str, str] = {}

    for offset, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if (offset & 255) == 0 or timeout_seconds < 1.0:
            if time.monotonic() - parse_start > timeout_seconds:
                raise StatementParseError(["CSV parsing timed out."])
        if not row or all(not c.strip() for c in row):
            continue

        raw_date = row[date_col].strip() if date_col < len(row) else ""
        raw_desc_cell = row[desc_col].strip() if (desc_col != -1 and desc_col < len(row)) else ""
        has_dr_cr = (debit_col != -1 and debit_col < len(row) and bool(row[debit_col].strip())) or (
            credit_col != -1 and credit_col < len(row) and bool(row[credit_col].strip())
        )
        has_amt = amount_col != -1 and amount_col < len(row) and bool(row[amount_col].strip())

        # Continuation line for multi-line narration
        if not raw_date and not has_dr_cr and not has_amt and raw_desc_cell and parsed_transactions:
            prev_tx = parsed_transactions[-1]
            combined_desc = f"{prev_tx['description']} {raw_desc_cell}".strip()
            category, merchant = categorize_transaction(combined_desc, prev_tx["transaction_type"])
            prev_tx["description"] = combined_desc
            prev_tx["description_cleaned"] = mask_sensitive_data(combined_desc)
            prev_tx["category"] = category
            prev_tx["merchant"] = merchant
            prev_tx["fingerprint"] = compute_transaction_fingerprint(
                account_id, prev_tx["date"], prev_tx["amount"], prev_tx["transaction_type"], combined_desc
            )
            continue

        if not raw_date:
            continue

        parsed_date, preferred_date_fmt = _try_parse_date(raw_date, preferred_date_fmt)
        if parsed_date is None:
            errors.append(f"Row {offset}: invalid date '{raw_date}'.")
            continue

        raw_desc = raw_desc_cell or "Bank Transaction"
        debit_val = 0.0
        credit_val = 0.0

        if debit_col != -1 and debit_col < len(row):
            d_val, _, d_ok = _parse_amount(row[debit_col])
            if not d_ok:
                errors.append(f"Row {offset}: invalid debit amount '{row[debit_col].strip()}'.")
                continue
            debit_val = d_val

        if credit_col != -1 and credit_col < len(row):
            c_val, _, c_ok = _parse_amount(row[credit_col])
            if not c_ok:
                errors.append(f"Row {offset}: invalid credit amount '{row[credit_col].strip()}'.")
                continue
            credit_val = c_val

        if debit_val == 0.0 and credit_val == 0.0 and amount_col != -1 and amount_col < len(row):
            amt, inferred_t, a_ok = _parse_amount(row[amount_col])
            if not a_ok:
                errors.append(f"Row {offset}: invalid amount '{row[amount_col].strip()}'.")
                continue
            t_type = inferred_t or "debit"
            if type_col != -1 and type_col < len(row):
                t_raw = row[type_col].strip().lower()
                if any(k in t_raw for k in ("cr", "credit", "deposit")):
                    t_type = "credit"
                elif any(k in t_raw for k in ("dr", "debit", "withdrawal")):
                    t_type = "debit"
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

        # Running balance validation
        if balance_col != -1 and balance_col < len(row) and row[balance_col].strip():
            bal_val, _, b_ok = _parse_amount(row[balance_col])
            if b_ok:
                if row[balance_col].strip().startswith("-"):
                    bal_val = -bal_val
                if prev_balance is not None:
                    expected_bal = prev_balance + amount if t_type == "credit" else prev_balance - amount
                    if abs(expected_bal - bal_val) > 0.05:
                        balance_warnings.append(
                            f"Row {offset}: running balance mismatch (expected {expected_bal:.2f}, got {bal_val:.2f})."
                        )
                prev_balance = bal_val

        cat_key = (raw_desc, t_type)
        cached_cat = cat_cache.get(cat_key)
        if cached_cat is None:
            cached_cat = categorize_transaction(raw_desc, t_type)
            cat_cache[cat_key] = cached_cat
        category, merchant = cached_cat

        masked_desc = mask_cache.get(raw_desc)
        if masked_desc is None:
            masked_desc = mask_sensitive_data(raw_desc)
            mask_cache[raw_desc] = masked_desc
        fingerprint = compute_transaction_fingerprint(account_id, parsed_date, amount, t_type, raw_desc)

        parsed_transactions.append(
            {
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
            }
        )

    if raise_on_row_error and errors:
        raise StatementParseError(errors)

    return StatementParseResult(
        transactions=parsed_transactions,
        errors=errors,
        balance_warnings=balance_warnings,
    )


def parse_csv_statement(content_str: str, account_id: str) -> list[dict[str, Any]]:
    """Parse a CSV bank statement with auto-detected columns."""
    res = parse_csv_statement_with_diagnostics(content_str, account_id, raise_on_row_error=False)
    if res.errors and not res.transactions:
        raise StatementParseError(res.errors)
    return res.transactions


def parse_pdf_statement(pdf_bytes: bytes, account_id: str) -> StatementParseResult:
    """Parse a text-based PDF bank statement safely without external dependencies."""
    if not pdf_bytes.startswith(b"%PDF-"):
        raise StatementParseError(["Invalid PDF file header."])
    if b"/Encrypt" in pdf_bytes:
        raise StatementParseError(["PDF is password-protected; please export an unlocked PDF or CSV."])

    extracted_lines: list[str] = []
    for match in PDF_STREAM_RE.finditer(pdf_bytes):
        raw_stream = match.group(1)
        try:
            decoded_stream = zlib.decompress(raw_stream).decode("latin-1", errors="ignore")
        except zlib.error:
            decoded_stream = raw_stream.decode("latin-1", errors="ignore")

        for op in PDF_TEXT_OP_RE.finditer(decoded_stream):
            if op.group(1) is not None:
                extracted_lines.append(op.group(1).replace("\\(", "(").replace("\\)", ")"))
            elif op.group(2) is not None:
                parts = PDF_TJ_STR_RE.findall(op.group(2))
                if parts:
                    extracted_lines.append("".join(parts).replace("\\(", "(").replace("\\)", ")"))

    # Also support plain-text lines inside uncompressed PDFs without Tj wrappers if present
    text_blob = "\n".join(line.strip() for line in extracted_lines if line.strip())
    if not text_blob:
        raise StatementParseError(
            ["Scanned or image-only PDF detected (no selectable text); please upload a text-based PDF or CSV."]
        )

    # Parse extracted PDF lines using CSV/semicolon or whitespace-delimited fallback
    csv_res = parse_csv_statement_with_diagnostics(text_blob, account_id, raise_on_row_error=False)
    if csv_res.transactions:
        return csv_res

    # Whitespace/pipe line fallback for PDFs whose table rows are emitted line-by-line across page breaks
    txs: list[dict[str, Any]] = []
    line_re = re.compile(
        r"^(\d{1,2}[/-][A-Za-z0-9]{2,3}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s+(DR|CR|DEBIT|CREDIT)\s*$",
        re.IGNORECASE,
    )
    for line in text_blob.splitlines():
        m = line_re.match(line.strip())
        if not m:
            continue
        dt, _ = _try_parse_date(m.group(1))
        if dt is None:
            continue
        desc = m.group(2).strip()
        amt, _, ok = _parse_amount(m.group(3))
        if not ok or amt <= 0:
            continue
        t_type = "credit" if m.group(4).lower() in ("cr", "credit") else "debit"
        cat, merch = categorize_transaction(desc, t_type)
        txs.append(
            {
                "account_id": account_id,
                "date": dt,
                "amount": amt,
                "transaction_type": t_type,
                "category": cat,
                "description": desc,
                "description_cleaned": mask_sensitive_data(desc),
                "merchant": merch,
                "fingerprint": compute_transaction_fingerprint(account_id, dt, amt, t_type, desc),
                "source": "pdf_upload",
                "is_recurring": False,
            }
        )
    return StatementParseResult(transactions=txs)


def parse_sms_statement(sms_text: str, account_id: str) -> dict[str, Any] | None:
    """Parse single Indian bank transaction alert SMS (HDFC, SBI, ICICI, Axis, Kotak, etc.)."""
    text = sms_text.strip()
    if not text:
        return None

    amt_match = re.search(r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if not amt_match:
        return None

    amt_str = amt_match.group(1).replace(",", "")
    amount = float(amt_str)

    t_type = "debit"
    if re.search(r"\b(credited|received|deposited|refunded)\b", text, re.IGNORECASE):
        t_type = "credit"

    merchant_pattern = r"(?:at|to|info\/|by)\s+([A-Za-z0-9\s.\-_]+?)(?:\s+on|\s+ref|\.|\s+avail|\s+bal)"
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
