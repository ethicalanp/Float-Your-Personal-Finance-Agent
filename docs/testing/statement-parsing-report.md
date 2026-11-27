# Synthetic Statement Parsing Report

- **Date**: 2026-11-27
- **Scope**: Strictly synthetic fixtures only (no real bank statements).
- **Suite**: [test_statement_parsing_suite.py](file:///d:/PersonalFinanceAgent/apps/api/tests/test_statement_parsing_suite.py) + [statement_parser.py](file:///d:/PersonalFinanceAgent/apps/api/app/services/statement_parser.py)

## Parse Success Table (Synthetic Fixtures)

| Fixture / Edge Case | Expected Outcome | Observed Result |
|---|---|---|
| **HDFC-like CSV** (`DD/MM/YYYY`, shifted 12-row header, lakh commas `1,25,000.50`, Dr/Cr, running balance) | 3/3 parsed, 0 balance warnings | **PASS** (3/3, 0 warnings) |
| **SBI-like CSV** (`DD-MMM-YY`, multi-line narration continuation, UPI narration) | 2/2 parsed, continuation merged | **PASS** (2/2) |
| **ICICI-like CSV** (signed `-2500.00`, `1500.00 Cr` suffix) | 2/2 parsed with correct debit/credit | **PASS** (2/2) |
| **Axis/Kotak-like CSV** (`;` delimiter, UTF-8 BOM, Windows-1252 `cp1252`) | Decoded & parsed cleanly | **PASS** (1/1 BOM, 1/1 cp1252) |
| **Multi-page PDF** (page break mid-table, `FlateDecode` streams) | 3/3 parsed across pages | **PASS** (3/3) |
| **Password-protected PDF** (`/Encrypt`) | Clear rejection error | **PASS** (`StatementParseError`) |
| **Scanned / image-only PDF** (no selectable text) | Clear rejection error | **PASS** (`StatementParseError`) |
| **Running-balance mismatch** | Row-numbered warning | **PASS** (`Row 3: running balance mismatch`) |
| **Invalid date / amount error** | User-facing `400` naming the row | **PASS** (`Row 2: invalid date ...`) |
| **Duplicate re-upload / overlapping period / multi-account** | Exact dedupe per account | **PASS** (2 skipped, 1+1 overlap, 2 on 2nd account) |
| **50,000-row synthetic CSV** | All 50,000 parsed under budget | **PASS** (50,000/50,000 in `17.35s`) |
