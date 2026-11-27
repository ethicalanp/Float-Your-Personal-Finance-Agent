import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.services.recurring_service import (
    detect_suggested_recurring,
    generate_schedule,
    get_due_date_for_month,
)


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    reg_data = {
        "email": "recurring_test@example.com",
        "password": "StrongPassword123!",
        "full_name": "Recurring Tester",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    res = client.post("/api/v1/auth/register", json=reg_data)
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_schedule_generation_due_dates() -> None:
    # Test month end bounds
    d_feb = get_due_date_for_month(2026, 2, 31)
    assert d_feb.day == 28

    d_apr = get_due_date_for_month(2026, 4, 31)
    assert d_apr.day == 30

    d_jan = get_due_date_for_month(2026, 1, 15)
    assert d_jan.day == 15


def test_schedule_frequency_intervals() -> None:
    c_id = uuid.uuid4()
    u_id = uuid.uuid4()

    # Quarterly: step by 3 months
    q_occs = generate_schedule(
        commitment_id=c_id,
        user_id=u_id,
        due_rule_day=5,
        expected_amount=Decimal("3000.00"),
        frequency="quarterly",
        start_date=date(2026, 1, 1),
        count=3,
    )
    assert len(q_occs) == 3
    assert q_occs[0].due_date == date(2026, 1, 5)
    assert q_occs[1].due_date == date(2026, 4, 5)
    assert q_occs[2].due_date == date(2026, 7, 5)

    # Yearly: step by 12 months
    y_occs = generate_schedule(
        commitment_id=c_id,
        user_id=u_id,
        due_rule_day=10,
        expected_amount=Decimal("12000.00"),
        frequency="yearly",
        start_date=date(2026, 3, 1),
        count=3,
    )
    assert len(y_occs) == 3
    assert y_occs[0].due_date == date(2026, 3, 10)
    assert y_occs[1].due_date == date(2027, 3, 10)
    assert y_occs[2].due_date == date(2028, 3, 10)

    # Weekly: step by 7 days
    w_occs = generate_schedule(
        commitment_id=c_id,
        user_id=u_id,
        due_rule_day=1,
        expected_amount=Decimal("500.00"),
        frequency="weekly",
        start_date=date(2026, 3, 1),
        count=3,
    )
    assert [o.due_date for o in w_occs] == [date(2026, 3, 1), date(2026, 3, 8), date(2026, 3, 15)]

    with pytest.raises(ValueError, match="Unsupported recurring frequency"):
        generate_schedule(
            commitment_id=c_id,
            user_id=u_id,
            due_rule_day=10,
            expected_amount=Decimal("100.00"),
            frequency="biweekly",
            start_date=date(2026, 3, 1),
        )


def test_candidate_suggestion_detection() -> None:
    base_date = datetime(2026, 1, 10, 10, 0, 0)
    mock_txs = [
        {"merchant": "Netflix", "amount": 649.0, "date": base_date.isoformat(), "transaction_type": "debit"},
        {
            "merchant": "Netflix",
            "amount": 649.0,
            "date": (base_date + timedelta(days=30)).isoformat(),
            "transaction_type": "debit",
        },
        {
            "merchant": "Netflix",
            "amount": 649.0,
            "date": (base_date + timedelta(days=60)).isoformat(),
            "transaction_type": "debit",
        },
    ]
    suggestions = detect_suggested_recurring(mock_txs)
    assert len(suggestions) == 1
    assert suggestions[0]["merchant"] == "Netflix"
    assert suggestions[0]["expected_amount"] == 649.0


def test_recurring_api_lifecycle(client: TestClient, auth_headers: dict[str, str]) -> None:
    # 1. Declare Commitment
    comm_res = client.post(
        "/api/v1/recurring/commitments",
        headers=auth_headers,
        json={
            "name": "Flat Rent",
            "category": "Rent & Housing",
            "amount_type": "fixed",
            "expected_amount": 15000.0,
            "frequency": "monthly",
            "due_rule_day": 5,
            "merchant": "Landlord",
        },
    )
    assert comm_res.status_code == 201
    comm_data = comm_res.json()
    commitment_id = comm_data["id"]
    assert comm_data["name"] == "Flat Rent"
    assert comm_data["expected_amount"] == 15000.0

    # 2. List commitments
    list_res = client.get("/api/v1/recurring/commitments", headers=auth_headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 3. List occurrences
    occ_res = client.get("/api/v1/recurring/occurrences", headers=auth_headers)
    assert occ_res.status_code == 200
    occurrences = occ_res.json()
    assert len(occurrences) >= 1
    assert occurrences[0]["status"] == "upcoming"
    assert occurrences[0]["expected_amount"] == 15000.0

    # 4. Create an account and upload a matching statement transaction
    acc_res = client.post(
        "/api/v1/plan/accounts",
        headers=auth_headers,
        json={
            "name": "Salary Account",
            "account_type": "savings",
            "institution_name": "HDFC",
            "account_number_mask": "****9999",
            "initial_balance": 50000.0,
        },
    )
    account_id = acc_res.json()["id"]

    # Target first occurrence due date
    first_due = occurrences[0]["due_date"]
    csv_content = f"""Date,Narration,Withdrawal,Deposit
{first_due},HOUSE RENT TRANSFER TO LANDLORD,15000.00,
"""
    upload_res = client.post(
        "/api/v1/plan/upload-statement",
        headers=auth_headers,
        json={"account_id": account_id, "format": "csv", "content": csv_content},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["imported_count"] == 1

    # 5. Verify occurrence is now marked paid
    occ_after_res = client.get("/api/v1/recurring/occurrences", headers=auth_headers)
    assert occ_after_res.status_code == 200
    paid_occurrences = [o for o in occ_after_res.json() if o["status"] == "paid"]
    assert len(paid_occurrences) == 1
    assert paid_occurrences[0]["paid_amount"] == 15000.0
    assert paid_occurrences[0]["paid_date"] == first_due

    # 6. Delete commitment
    del_res = client.delete(f"/api/v1/recurring/commitments/{commitment_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # List should now be empty
    list_after = client.get("/api/v1/recurring/commitments", headers=auth_headers)
    assert len(list_after.json()) == 0

    canceled_occurrences = client.get("/api/v1/recurring/occurrences", headers=auth_headers).json()
    assert any(occurrence["status"] == "cancelled" for occurrence in canceled_occurrences)

    sync_res = client.post("/api/v1/recurring/sync", headers=auth_headers)
    assert sync_res.status_code == 200
    assert sync_res.json()["notifications_generated"] == 0
    assert sync_res.json()["occurrences_replenished"] == 0


def test_sync_notifications_are_idempotent_and_can_be_read(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    tomorrow = date.today() + timedelta(days=1)
    commitment_res = client.post(
        "/api/v1/recurring/commitments",
        headers=auth_headers,
        json={
            "name": "Internet",
            "expected_amount": 1200,
            "due_rule_day": tomorrow.day,
            "frequency": "monthly",
        },
    )
    assert commitment_res.status_code == 201

    sync_res = client.post("/api/v1/recurring/sync", headers=auth_headers)
    assert sync_res.status_code == 200
    assert sync_res.json()["notifications_generated"] == 1

    unread_res = client.get(
        "/api/v1/recurring/notifications?unread_only=true",
        headers=auth_headers,
    )
    assert unread_res.status_code == 200
    notification = unread_res.json()[0]
    assert notification["is_read"] is False
    assert "Internet" in notification["message"]

    repeated_sync = client.post("/api/v1/recurring/sync", headers=auth_headers)
    assert repeated_sync.json()["notifications_generated"] == 0

    read_res = client.patch(
        f"/api/v1/recurring/notifications/{notification['id']}/read",
        headers=auth_headers,
    )
    assert read_res.status_code == 204
    assert (
        client.get(
            "/api/v1/recurring/notifications?unread_only=true",
            headers=auth_headers,
        ).json()
        == []
    )

    commitment_id = commitment_res.json()["id"]
    deactivate_res = client.delete(
        f"/api/v1/recurring/commitments/{commitment_id}",
        headers=auth_headers,
    )
    assert deactivate_res.status_code == 204
    assert (
        client.get(
            "/api/v1/recurring/notifications",
            headers=auth_headers,
        ).json()
        == []
    )
