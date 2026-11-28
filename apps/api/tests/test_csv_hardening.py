import csv

import pytest

from app.ai.evals.models import RAGEvalCase
from app.ai.evals.review import export_drafts_to_csv
from app.services.statement_parser import (
    StatementParseError,
    escape_csv_formula,
    parse_csv_statement_with_diagnostics,
)


def test_csv_size_and_row_count_caps() -> None:
    csv_text = "Date,Description,Debit,Credit\n01/01/2026,Coffee,100,\n02/01/2026,Tea,50,\n"
    with pytest.raises(StatementParseError, match="exceeds maximum allowed"):
        parse_csv_statement_with_diagnostics(csv_text, account_id="acc-1", max_bytes=20)

    with pytest.raises(StatementParseError, match="row count"):
        parse_csv_statement_with_diagnostics(csv_text, account_id="acc-1", max_rows=2)


def test_csv_parse_timeout() -> None:
    rows = ["Date,Description,Debit,Credit"] + [f"01/01/2026,Item {i},10," for i in range(50)]
    csv_text = "\n".join(rows)
    with pytest.raises(StatementParseError, match="timed out"):
        parse_csv_statement_with_diagnostics(csv_text, account_id="acc-1", timeout_seconds=0.0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("=CMD|'/C calc'!A0", "'=CMD|'/C calc'!A0"),
        ("+SUM(A1:A2)", "'+SUM(A1:A2)"),
        ("-1+1", "'-1+1"),
        ("@SUM(1,2)", "'@SUM(1,2)"),
        ("  =HYPERLINK()", "'  =HYPERLINK()"),
        ("Normal Merchant", "Normal Merchant"),
        ("", ""),
    ],
)
def test_csv_formula_escaping(raw: str, expected: str) -> None:
    assert escape_csv_formula(raw) == expected


def test_export_drafts_to_csv_escapes_formula_triggers(tmp_path) -> None:
    case = RAGEvalCase(
        id="case-1",
        language="en",
        type="answerable",
        question="=CMD|'calc'!A0",
        reference_answer="+100",
        gold_chunk_id="chunk-1",
        required_facts=["-fact"],
        status="draft",
        review_notes="@note",
        split="dev",
        needs_native_review=False,
    )
    out = tmp_path / "export.csv"
    export_drafts_to_csv([case], out)
    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["question"].startswith("'=")
    assert rows[0]["reference_answer"].startswith("'+")
    assert rows[0]["review_notes"].startswith("'@")
