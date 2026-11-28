import time
import uuid
import zlib

import pytest
from fastapi.testclient import TestClient

from app.services.statement_parser import (
    StatementParseError,
    parse_csv_statement_with_diagnostics,
    parse_pdf_statement,
)


def _register_and_consent(client: TestClient, prefix: str) -> dict[str, str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123!", "full_name": "Parse User"},
    )
    assert res.status_code == 201
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    c_res = client.post(
        "/api/v1/auth/consent",
        headers=headers,
        json={"terms_accepted": True, "privacy_accepted": True, "ai_data_processing_consent": True},
    )
    assert c_res.status_code == 200
    return headers


def _build_synthetic_pdf(page_streams: list[str], encrypted: bool = False) -> bytes:
    parts = [b"%PDF-1.4\n"]
    if encrypted:
        parts.append(b"1 0 obj << /Encrypt 2 0 R >> endobj\n")
    for idx, content in enumerate(page_streams, start=1):
        compressed = zlib.compress(content.encode("latin-1"))
        parts.append(f"{idx + 1} 0 obj << /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode())
        parts.append(compressed)
        parts.append(b"\nendstream\nendobj\n")
    parts.append(b"%%EOF\n")
    return b"".join(parts)


def test_major_bank_layouts_lakh_commas_shifted_headers_multiline_and_encodings() -> None:
    # 1. HDFC-like: shifted header (12 preamble lines), DD/MM/YYYY, lakh commas, Dr/Cr columns, running balance
    hdfc_csv = "\n".join(
        [f"Metadata line {i}" for i in range(12)]
        + [
            "Txn Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance",
            '01/11/2026,"SALARY CREDIT ACME CORP","0.00","1,25,000.50","1,50,000.50"',
            '02/11/2026,"UPI-SWIGGY-123456","450.00","","1,49,550.50"',
            '03/11/2026,"UPI/DR/987654/AIRTEL POSTPAID","1,199.00","","1,48,351.50"',
        ]
    )
    r_hdfc = parse_csv_statement_with_diagnostics(hdfc_csv, "acc-hdfc")
    assert len(r_hdfc.transactions) == 3
    assert r_hdfc.transactions[0]["amount"] == 125000.50
    assert r_hdfc.transactions[0]["transaction_type"] == "credit"
    assert r_hdfc.balance_warnings == []

    # 2. SBI-like: DD-MMM-YY, multi-line narration continuation
    sbi_csv = (
        "Txn Date,Description,Debit,Credit\n"
        "05-Nov-26,UPI/DR/445566/ZOMATO,320.00,\n"
        ",ORDER #889911 KORAMANGALA,,\n"
        "06-Nov-26,NEFT SALARY,0.00,85000.00\n"
    )
    r_sbi = parse_csv_statement_with_diagnostics(sbi_csv, "acc-sbi")
    assert len(r_sbi.transactions) == 2
    assert "ORDER #889911 KORAMANGALA" in r_sbi.transactions[0]["description"]
    assert r_sbi.transactions[1]["transaction_type"] == "credit"

    # 3. ICICI-like: signed amounts and Dr/Cr suffix
    icici_csv = (
        "Date,Particulars,Amount\n"
        "10/11/2026,ATM CASH WDL,-2500.00\n"
        "11/11/2026,DIVIDEND CREDIT,1500.00 Cr\n"
    )
    r_icici = parse_csv_statement_with_diagnostics(icici_csv, "acc-icici")
    assert len(r_icici.transactions) == 2
    assert r_icici.transactions[0]["transaction_type"] == "debit"
    assert r_icici.transactions[1]["transaction_type"] == "credit"

    # 4. Axis/Kotak-like: semicolon delimiter + UTF-8 BOM and Windows-1252 bytes
    bom_csv = "\ufeffDate;Remarks;Amount;Type\n12-11-2026;Café Coffee Day;240.00;Dr\n".encode("utf-8")
    r_bom = parse_csv_statement_with_diagnostics(bom_csv, "acc-axis")
    assert len(r_bom.transactions) == 1
    assert r_bom.transactions[0]["amount"] == 240.00

    win_csv = "Date;Remarks;Amount;Type\n12-11-2026;Café Coffee Day – Indiranagar;240.00;Dr\n".encode("cp1252")
    r_win = parse_csv_statement_with_diagnostics(win_csv, "acc-axis")
    assert len(r_win.transactions) == 1
    assert r_win.transactions[0]["amount"] == 240.00


def test_pdf_multipage_password_and_scanned_rejections() -> None:
    # Multi-page PDF with page break mid-table
    p1 = "BT (01/11/2026 UPI-NETFLIX-AUTOPAY 649.00 DR) Tj (02/11/2026 SALARY) Tj ET"
    p2 = "BT (02/11/2026 SALARY-CREDIT 90,000.00 CR) Tj (03/11/2026 KSEB BILL 1,250.00 DR) Tj ET"
    pdf_ok = _build_synthetic_pdf([p1, p2])
    res = parse_pdf_statement(pdf_ok, "acc-pdf")
    assert len(res.transactions) == 3

    # Password-protected PDF
    pdf_enc = _build_synthetic_pdf([p1], encrypted=True)
    with pytest.raises(StatementParseError, match="password-protected"):
        parse_pdf_statement(pdf_enc, "acc-pdf")

    # Scanned / image-only PDF (no Tj/TJ text)
    pdf_scan = _build_synthetic_pdf(["q 100 0 0 100 0 0 cm /Im1 Do Q"])
    with pytest.raises(StatementParseError, match="Scanned or image-only PDF"):
        parse_pdf_statement(pdf_scan, "acc-pdf")


def test_running_balance_mismatch_and_row_named_errors(client: TestClient) -> None:
    bad_bal_csv = (
        "Date,Description,Debit,Credit,Balance\n"
        "01/11/2026,Opening Credit,,10000.00,10000.00\n"
        "02/11/2026,Mis-parsed Row,500.00,,5000.00\n"
    )
    bal_res = parse_csv_statement_with_diagnostics(bad_bal_csv, "acc-bal")
    assert len(bal_res.balance_warnings) == 1
    assert "Row 3: running balance mismatch" in bal_res.balance_warnings[0]

    # Row-named error on invalid date/amount
    bad_date_csv = "Date,Description,Debit,Credit\n99-99-9999,Bad Date Row,100.00,\n"
    with pytest.raises(StatementParseError, match="Row 2: invalid date"):
        parse_csv_statement_with_diagnostics(bad_date_csv, "acc-err", raise_on_row_error=True)

    # Endpoint surfaces row-named error on 400
    headers = _register_and_consent(client, "parseerr")
    acc = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={"name": "HDFC", "account_type": "savings", "institution_name": "HDFC", "account_number_mask": "****5555"},
    ).json()
    up_err = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": acc["id"], "format": "csv", "content": bad_date_csv},
    )
    assert up_err.status_code == 400
    assert "Row 2" in up_err.json()["error"]["message"]


def test_duplicate_reupload_overlapping_periods_and_multiple_accounts(client: TestClient) -> None:
    headers = _register_and_consent(client, "dups")
    acc1 = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={"name": "HDFC", "account_type": "savings", "institution_name": "HDFC", "account_number_mask": "****1111"},
    ).json()
    acc2 = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={"name": "SBI", "account_type": "savings", "institution_name": "SBI", "account_number_mask": "****2222"},
    ).json()

    csv_p1 = "Date,Description,Amount,Type\n2026-11-01,Swiggy,400,debit\n2026-11-02,Metro,60,debit\n"
    r1 = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": acc1["id"], "format": "csv", "content": csv_p1},
    )
    assert r1.status_code == 200
    assert r1.json()["imported_count"] == 2

    # Exact duplicate re-upload -> 0 imported, 2 skipped
    r_dup = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": acc1["id"], "format": "csv", "content": csv_p1},
    )
    assert r_dup.status_code == 200
    assert r_dup.json()["imported_count"] == 0
    assert r_dup.json()["duplicates_skipped"] == 2

    # Overlapping period -> skips 11-02, imports 11-03
    csv_overlap = "Date,Description,Amount,Type\n2026-11-02,Metro,60,debit\n2026-11-03,Bookstore,350,debit\n"
    r_ov = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": acc1["id"], "format": "csv", "content": csv_overlap},
    )
    assert r_ov.status_code == 200
    assert r_ov.json()["imported_count"] == 1
    assert r_ov.json()["duplicates_skipped"] == 1

    # Multiple accounts -> same CSV on acc2 imports cleanly without cross-account deduping
    r_acc2 = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": acc2["id"], "format": "csv", "content": csv_p1},
    )
    assert r_acc2.status_code == 200
    assert r_acc2.json()["imported_count"] == 2


@pytest.mark.slow
def test_50k_row_parse_performance() -> None:
    base_lines = ["Date,Description,Debit,Credit"] + [
        f"2026-11-{(i % 28) + 1:02d},UPI/DR/{i}/MERCHANT_{i % 50},{(i % 900) + 10}.00,"
        for i in range(5_000)
    ]
    t_base0 = time.perf_counter()
    base_res = parse_csv_statement_with_diagnostics("\n".join(base_lines), "acc-5k")
    elapsed_5k = max(time.perf_counter() - t_base0, 0.01)
    assert len(base_res.transactions) == 5_000

    lines = ["Date,Description,Debit,Credit"] + [
        f"2026-11-{(i % 28) + 1:02d},UPI/DR/{i}/MERCHANT_{i % 50},{(i % 900) + 10}.00,"
        for i in range(50_000)
    ]
    big_csv = "\n".join(lines)
    t0 = time.perf_counter()
    res = parse_csv_statement_with_diagnostics(big_csv, "acc-50k")
    elapsed = time.perf_counter() - t0
    assert len(res.transactions) == 50_000
    assert elapsed < max(60.0, elapsed_5k * 20.0), (
        f"50k-row parse took {elapsed:.2f}s (5k baseline={elapsed_5k:.2f}s)"
    )
