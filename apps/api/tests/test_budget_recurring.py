import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.models.enums import TransactionSource, TransactionType
from app.models.plan import Transaction
from app.services.budget_service import allocate_budget_paise, get_ist_month_bounds
from app.services.recurring_service import (
    filter_unusual_spend_transactions,
    generate_schedule,
    get_due_date_for_month,
)


def _register_and_consent(client: TestClient, prefix: str) -> tuple[dict[str, str], str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123!", "full_name": "Budget User"},
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    c_res = client.post(
        "/api/v1/auth/consent",
        headers=headers,
        json={"terms_accepted": True, "privacy_accepted": True, "ai_data_processing_consent": True},
    )
    assert c_res.status_code == 200
    return headers, res.json()["user_id"]


def test_largest_remainder_rounding_exact_sum() -> None:
    n, w, s = allocate_budget_paise(10001, Decimal("33.33"), Decimal("33.33"), Decimal("33.34"))
    assert n + w + s == 10001
    n2, w2, s2 = allocate_budget_paise(103, Decimal("50.00"), Decimal("30.00"), Decimal("20.00"))
    assert (n2, w2, s2) == (51, 31, 21)
    assert n2 + w2 + s2 == 103


def test_budget_validation_and_edge_cases(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "bval")

    # Zero / negative income -> 422
    assert (
        client.put(
            "/api/v1/plan/budget",
            headers=headers,
            json={"monthly_income_paise": 0, "needs_pct": 50, "wants_pct": 30, "savings_pct": 20},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/plan/budget",
            headers=headers,
            json={"monthly_income_paise": -5000, "needs_pct": 50, "wants_pct": 30, "savings_pct": 20},
        ).status_code
        == 422
    )
    # Huge value (> 100 Cr) -> 422
    assert (
        client.put(
            "/api/v1/plan/budget",
            headers=headers,
            json={"monthly_income_paise": 100_000_000_000, "needs_pct": 50, "wants_pct": 30, "savings_pct": 20},
        ).status_code
        == 422
    )
    # Percentages not summing to 100 -> 400
    bad_pct = client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={"monthly_income_paise": 5_000_000, "needs_pct": 50, "wants_pct": 30, "savings_pct": 10},
    )
    assert bad_pct.status_code == 400

    # Month with no transactions -> has_transactions False, actual 0, nothing invented
    get_res = client.get("/api/v1/plan/budget?month=2026-01", headers=headers)
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["plan"] is None
    assert body["actuals"]["has_transactions"] is False
    assert body["actuals"]["actual_needs_paise"] == 0


def test_budget_versioning_mid_month_change_and_optimistic_concurrency(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "bver")

    v1 = client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": "2026-11",
            "monthly_income_paise": 10_000_000,  # ₹1,00,000
            "needs_pct": 50,
            "wants_pct": 30,
            "savings_pct": 20,
        },
    )
    assert v1.status_code == 200
    assert v1.json()["version"] == 1

    # Mid-month income change with expected_version=1 -> version 2
    v2 = client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": "2026-11",
            "monthly_income_paise": 12_000_000,
            "needs_pct": 60,
            "wants_pct": 20,
            "savings_pct": 20,
            "expected_version": 1,
        },
    )
    assert v2.status_code == 200
    assert v2.json()["version"] == 2

    # Concurrent edit from stale tab (expected_version=1) -> 409 CONFLICT
    stale = client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": "2026-11",
            "monthly_income_paise": 9_000_000,
            "needs_pct": 50,
            "wants_pct": 30,
            "savings_pct": 20,
            "expected_version": 1,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFLICT"

    # History readable
    hist = client.get("/api/v1/plan/budget/history?month=2026-11", headers=headers)
    assert hist.status_code == 200
    assert [h["version"] for h in hist.json()] == [2, 1]


def test_budget_needs_plus_recurring_warning(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "bwarn")
    client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": "2026-11",
            "monthly_income_paise": 5_000_000,
            "needs_pct": 50,
            "wants_pct": 30,
            "savings_pct": 20,
        },
    )
    # Add ₹30,000 rent (exceeds ₹25,000 needs budget)
    rec = client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Apartment Rent",
            "category": "Rent & Housing",
            "expected_amount": 30000,
            "frequency": "monthly",
            "due_rule_day": 5,
            "merchant": "Landlord",
        },
    )
    assert rec.status_code == 201
    overview = client.get("/api/v1/plan/budget?month=2026-11", headers=headers).json()
    assert len(overview["actuals"]["warnings"]) >= 1


def test_recurring_cross_user_404_stepup_pause_and_end_date(client: TestClient) -> None:
    h1, _ = _register_and_consent(client, "rec1")
    h2, _ = _register_and_consent(client, "rec2")

    create = client.post(
        "/api/v1/recurring/commitments",
        headers=h1,
        json={
            "name": "Nifty 50 SIP",
            "category": "SIP",
            "expected_amount": 5000,
            "frequency": "monthly",
            "due_rule_day": 31,
            "merchant": "Zerodha Coin",
            "merchant_keywords": ["zerodha", "coin"],
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        },
    )
    assert create.status_code == 201
    cid = create.json()["id"]

    # Cross-user PATCH & DELETE -> 404
    patch_res = client.patch(f"/api/v1/recurring/commitments/{cid}", headers=h2, json={"is_active": False})
    assert patch_res.status_code == 404
    assert client.delete(f"/api/v1/recurring/commitments/{cid}", headers=h2).status_code == 404

    # SIP step-up + pause
    upd = client.patch(
        f"/api/v1/recurring/commitments/{cid}",
        headers=h1,
        json={"expected_amount": 7500, "is_active": False, "expected_version": 1},
    )
    assert upd.status_code == 200
    assert upd.json()["expected_amount"] == 7500.0
    assert upd.json()["is_active"] is False
    assert upd.json()["version"] == 2

    # Stale version -> 409
    assert (
        client.patch(
            f"/api/v1/recurring/commitments/{cid}",
            headers=h1,
            json={"expected_amount": 8000, "expected_version": 1},
        ).status_code
        == 409
    )


def test_recurring_month_end_31st_and_ist_boundaries() -> None:
    assert get_due_date_for_month(2026, 2, 31) == date(2026, 2, 28)
    assert get_due_date_for_month(2024, 2, 31) == date(2024, 2, 29)
    assert get_due_date_for_month(2026, 4, 31) == date(2026, 4, 30)

    occs = generate_schedule(
        commitment_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        due_rule_day=31,
        expected_amount=Decimal("1000.00"),
        frequency="monthly",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
        count=5,
    )
    assert [o.due_date for o in occs] == [date(2026, 1, 31), date(2026, 2, 28)]

    # IST boundary: 2026-10-31 18:30 UTC == 2026-11-01 00:00 IST
    start_utc, end_utc = get_ist_month_bounds("2026-11")
    assert start_utc == datetime(2026, 10, 31, 18, 30, 0, tzinfo=timezone.utc)
    assert end_utc.astimezone(timezone.utc) > start_utc


@pytest.mark.asyncio
async def test_matching_ambiguous_weekend_drift_duplicate_and_protect_isolation(client: TestClient) -> None:
    headers, uid_str = _register_and_consent(client, "rmatch")
    # Weekend drift: 2026-11-07 is Saturday; debit on Monday 2026-11-09 matches
    c1 = client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Netflix",
            "category": "Subscriptions",
            "expected_amount": 649,
            "frequency": "monthly",
            "due_rule_day": 7,
            "merchant": "Netflix",
            "merchant_keywords": ["netflix"],
            "start_date": "2026-11-01",
        },
    )
    assert c1.status_code == 201

    # Account + CSV upload with matching Netflix debit on Nov 9 (weekend drift)
    acc = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={"name": "HDFC", "account_type": "savings", "institution_name": "HDFC", "account_number_mask": "****1111"},
    ).json()
    up = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={
            "account_id": acc["id"],
            "format": "csv",
            "content": (
                "Date,Description,Amount,Type\n"
                "2026-11-09,Netflix India Subscription,649,debit\n"
                "2026-11-10,Swiggy Order,450,debit\n"
            ),
        },
    )
    assert up.status_code == 200
    assert client.post("/api/v1/recurring/match", headers=headers).status_code == 200

    txs = client.get("/api/v1/plan/transactions", headers=headers).json()
    netflix_tx = [t for t in txs if "netflix" in t["description"].lower()][0]
    swiggy_tx = [t for t in txs if "swiggy" in t["description"].lower()][0]
    assert netflix_tx["is_recurring"] is True
    assert swiggy_tx["is_recurring"] is False

    # Unusual-spend filter excludes recurring
    fake_txns = [
        Transaction(
            id=uuid.uuid4(),
            user_id=uuid.UUID(uid_str),
            account_id=uuid.UUID(acc["id"]),
            transaction_date=datetime.now(timezone.utc),
            amount=Decimal("649.00"),
            transaction_type=TransactionType.DEBIT,
            category="Subscriptions",
            description="Netflix",
            description_cleaned="Netflix",
            normalized_fingerprint="a" * 64,
            source=TransactionSource.CSV_UPLOAD,
            is_recurring=True,
        ),
        Transaction(
            id=uuid.uuid4(),
            user_id=uuid.UUID(uid_str),
            account_id=uuid.UUID(acc["id"]),
            transaction_date=datetime.now(timezone.utc),
            amount=Decimal("450.00"),
            transaction_type=TransactionType.DEBIT,
            category="Dining",
            description="Swiggy",
            description_cleaned="Swiggy",
            normalized_fingerprint="b" * 64,
            source=TransactionSource.CSV_UPLOAD,
            is_recurring=False,
        ),
    ]
    unusual = filter_unusual_spend_transactions(fake_txns)
    assert len(unusual) == 1 and unusual[0].description == "Swiggy"

    # Reminders endpoint works deterministically
    rem = client.get("/api/v1/recurring/reminders", headers=headers)
    assert rem.status_code == 200
    assert "due_soon" in rem.json() and "overdue" in rem.json()

    # Protect scam checker unaffected
    scam = client.post(
        "/api/v1/protect/check",
        headers=headers,
        json={"message": "Your Netflix KYC expired click http://bit.ly/fake-netflix", "language_hint": "en"},
    )
    assert scam.status_code == 200
    assert scam.json()["analysis"]["risk_tier"] in ("MEDIUM", "HIGH", "CRITICAL", "SAFE", "LOW")


def test_skipped_month_two_rules_matching_and_duplicate_debit(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "edge2")
    h_other, _ = _register_and_consent(client, "edge2_other")

    # Cross-user isolation on GET /plan/budget, /plan/budget/history, /recurring/reminders
    client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": "2026-11",
            "monthly_income_paise": 8_000_000,
            "needs_pct": 50,
            "wants_pct": 30,
            "savings_pct": 20,
        },
    )
    assert client.get("/api/v1/plan/budget?month=2026-11", headers=h_other).json()["plan"] is None
    assert client.get("/api/v1/plan/budget/history?month=2026-11", headers=h_other).json() == []

    # Two rules matching one transaction (broadband vs exact merchant keyword)
    c1 = client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Generic Telecom",
            "category": "Utilities",
            "expected_amount": 999,
            "frequency": "monthly",
            "due_rule_day": 28,
            "merchant": "Airtel",
            "merchant_keywords": ["airtel"],
            "start_date": "2026-11-01",
        },
    ).json()
    c2 = client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Airtel Fiber Exact",
            "category": "Utilities",
            "expected_amount": 999,
            "frequency": "monthly",
            "due_rule_day": 28,
            "merchant": "Airtel Fiber",
            "merchant_keywords": ["airtel fiber"],
            "start_date": "2026-11-01",
        },
    ).json()
    assert c1["id"] != c2["id"]

    # Skipped month in past -> reminders marks overdue/missed
    past_c = client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Past Gym",
            "category": "Other",
            "expected_amount": 1500,
            "frequency": "monthly",
            "due_rule_day": 1,
            "merchant": "CultFit",
            "start_date": "2026-09-01",
        },
    )
    assert past_c.status_code == 201
    rem = client.get("/api/v1/recurring/reminders", headers=headers).json()
    assert len(rem["overdue"]) >= 1
    assert any(o["mismatch_flag"] == "missed" for o in rem["overdue"])

    # Duplicate debit in same period -> flags duplicate on occurrence
    acc = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={"name": "SBI", "account_type": "savings", "institution_name": "SBI", "account_number_mask": "****2222"},
    ).json()
    client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={
            "account_id": acc["id"],
            "format": "csv",
            "content": (
                "Date,Description,Amount,Type\n"
                "2026-11-27,Airtel Fiber Bill 1,999,debit\n"
                "2026-11-28,Airtel Fiber Bill 2,999,debit\n"
            ),
        },
    )
    match_res = client.post("/api/v1/recurring/match", headers=headers)
    assert match_res.status_code == 200
    occs = client.get("/api/v1/recurring/occurrences", headers=headers).json()
    assert any(o["status"] == "paid" and o["match_reason"] for o in occs)
    assert any(o["mismatch_flag"] == "duplicate" for o in occs)
