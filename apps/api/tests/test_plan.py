from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.services.cash_flow import compute_financial_insights, compute_monthly_cash_flow
from app.services.categorizer import categorize_transaction
from app.services.data_sanitizer import mask_sensitive_data
from app.services.deduplication import compute_transaction_fingerprint
from app.services.statement_parser import parse_csv_statement, parse_sms_statement


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = create_access_token(
        subject="test-user-uuid",
        claims={"email": "plan_test@example.com", "full_name": "Test User", "consent_given": True},
    )
    return {"Authorization": f"Bearer {token}"}


def test_data_sanitization_masks_pii() -> None:
    sample_text = (
        "Spent Rs 1500 at Swiggy from A/c 5010023456789012. "
        "Paid to john.doe@okaxis via phone 9876543210. Card 4111222233334444. "
        "Contact me at anupam@gmail.com."
    )
    masked = mask_sensitive_data(sample_text)

    assert "9876543210" not in masked
    assert "+91-XXXXX-X3210" in masked or "XXXXX" in masked
    assert "4111222233334444" not in masked
    assert "****-****-****-4444" in masked
    assert "john.doe@okaxis" not in masked
    assert "anupam@gmail.com" not in masked
    assert "5010023456789012" not in masked


def test_transaction_categorization() -> None:
    cat, merchant = categorize_transaction("Swiggy Order #12345", "debit")
    assert cat == "Food & Dining"
    assert merchant == "Swiggy"

    cat, _ = categorize_transaction("Blinkit Commerce Instant Delivery", "debit")
    assert cat == "Groceries"

    cat, _ = categorize_transaction("Monthly House Rent Transfer", "debit")
    assert cat == "Rent & Housing"

    cat, _ = categorize_transaction("Salary Credit for March 2026", "credit")
    assert cat == "Income & Salary"

    cat, _ = categorize_transaction("BESCOM Electricity Bill Payment", "debit")
    assert cat == "Utilities"


def test_deduplication_fingerprint() -> None:
    dt = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
    fp1 = compute_transaction_fingerprint("acc-1", dt, 500.0, "debit", "Swiggy order")
    fp2 = compute_transaction_fingerprint("acc-1", dt, 500.0, "debit", "Swiggy   ORDER ")
    fp3 = compute_transaction_fingerprint("acc-1", dt, 501.0, "debit", "Swiggy order")

    assert fp1 == fp2  # normalized match
    assert fp1 != fp3  # different amount


def test_statement_parsing_csv() -> None:
    csv_sample = """Date,Narration,Withdrawal,Deposit
2026-03-01,SALARY CREDIT FROM TECH CORP,,75000.00
2026-03-02,SWIGGY BANGALORE,450.00,
2026-03-03,BLINKIT INSTAMART,1200.00,
"""
    txs = parse_csv_statement(csv_sample, "acc-1")
    assert len(txs) == 3
    assert txs[0]["category"] == "Income & Salary"
    assert txs[0]["amount"] == 75000.0
    assert txs[1]["category"] == "Food & Dining"
    assert txs[2]["category"] == "Groceries"


def test_statement_parsing_sms() -> None:
    sms = "Rs. 650.00 spent on HDFC Bank Card ending 1234 at Zomato on 02-Mar-26. Avail Bal: Rs 42,000.00"
    tx = parse_sms_statement(sms, "acc-1")
    assert tx is not None
    assert tx["amount"] == 650.0
    assert tx["transaction_type"] == "debit"
    assert tx["category"] == "Food & Dining"


def test_cash_flow_and_insights_computation() -> None:
    mock_txs = [
        {"date": "2026-01-01", "amount": 80000.0, "transaction_type": "credit", "category": "Income & Salary"},
        {"date": "2026-01-15", "amount": 25000.0, "transaction_type": "debit", "category": "Rent & Housing"},
        {"date": "2026-01-20", "amount": 5000.0, "transaction_type": "debit", "category": "Food & Dining"},
        {"date": "2026-02-01", "amount": 80000.0, "transaction_type": "credit", "category": "Income & Salary"},
        {"date": "2026-02-10", "amount": 30000.0, "transaction_type": "debit", "category": "Rent & Housing"},
    ]
    cash_flow = compute_monthly_cash_flow(mock_txs)
    assert cash_flow["total_inflow"] == 160000.0
    assert cash_flow["total_outflow"] == 60000.0
    assert cash_flow["net_savings"] == 100000.0

    insights = compute_financial_insights(mock_txs, current_balance=100000.0)
    assert insights["income_volatility"]["tier"] == "LOW"
    assert insights["balance_buffer"]["runway_months"] > 3.0
    assert insights["balance_buffer"]["status"] == "HEALTHY"
    assert len(insights["top_spending_categories"]) > 0
    assert insights["top_spending_categories"][0]["category"] == "Rent & Housing"


def test_plan_api_flow(client: TestClient, auth_headers: dict[str, str]) -> None:
    # 1. Create account
    acc_res = client.post(
        "/api/v1/plan/accounts",
        headers=auth_headers,
        json={
            "name": "Main Checking",
            "account_type": "savings",
            "institution_name": "HDFC Bank",
            "account_number_mask": "****5678",
            "initial_balance": 50000.0,
        },
    )
    assert acc_res.status_code == 201
    account_id = acc_res.json()["id"]

    # 2. Upload statement
    csv_data = """Date,Narration,Withdrawal,Deposit
2026-03-01,SALARY MARCH,,85000.00
2026-03-02,SWIGGY FOOD,500.00,
"""
    upload_res = client.post(
        "/api/v1/plan/upload-statement",
        headers=auth_headers,
        json={"account_id": account_id, "format": "csv", "content": csv_data},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["imported_count"] == 2

    # 3. Duplicate upload should skip
    dup_res = client.post(
        "/api/v1/plan/upload-statement",
        headers=auth_headers,
        json={"account_id": account_id, "format": "csv", "content": csv_data},
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["imported_count"] == 0
    assert dup_res.json()["duplicates_skipped"] == 2

    # 4. Cash Flow & Insights APIs
    cf_res = client.get("/api/v1/plan/cash-flow", headers=auth_headers)
    assert cf_res.status_code == 200
    assert cf_res.json()["total_inflow"] == 85000.0

    insights_res = client.get("/api/v1/plan/insights", headers=auth_headers)
    assert insights_res.status_code == 200
    assert "balance_buffer" in insights_res.json()
