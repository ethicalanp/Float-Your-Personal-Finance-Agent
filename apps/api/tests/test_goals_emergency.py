from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.ai.agent.models import RouteClass
from app.ai.agent.planner import create_deterministic_plan
from app.services.goals_service import (
    allocate_budget_across_goals,
    compute_months_remaining,
    suggested_monthly_largest_remainder,
)


def _register_and_consent(client: TestClient, tag: str) -> tuple[dict[str, str], str]:
    email = f"ge_{tag}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"Goals {tag}"},
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


def test_largest_remainder_and_ist_month_boundaries() -> None:
    # 10,000 paise over 3 months -> 3334 (ceiling for remainder)
    assert suggested_monthly_largest_remainder(10000, 3) == 3334
    assert suggested_monthly_largest_remainder(10000, 0) == 10000
    assert suggested_monthly_largest_remainder(0, 6) == 0

    # IST boundary: 2026-11-30 19:00 UTC is already 2026-12-01 00:30 IST
    ist_dec1 = datetime(2026, 11, 30, 19, 0, tzinfo=UTC).astimezone(ZoneInfo("Asia/Kolkata")).date()
    assert ist_dec1 == date(2026, 12, 1)
    m, past = compute_months_remaining(date(2026, 12, 15), ist_dec1)
    assert m == 0 and past is False
    m_past, is_past = compute_months_remaining(date(2026, 11, 30), ist_dec1)
    assert m_past == 0 and is_past is True

    # Priority allocation cap
    assert allocate_budget_across_goals([15000, 10000], 20000) == [15000, 5000]


def test_goals_crud_conflict_oversaved_past_due_and_409(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "crud")
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    ist_month = today_ist.strftime("%Y-%m")

    # Set budget savings share = ₹20,000 (2,000,000 paise)
    b_res = client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": ist_month,
            "monthly_income_paise": 10_000_000,
            "needs_pct": 50,
            "wants_pct": 30,
            "savings_pct": 20,
        },
    )
    assert b_res.status_code == 200

    # Goal 1: past due date, over-saved -> is_funded=True, suggested_monthly_paise=0
    g1 = client.post(
        "/api/v1/plan/goals",
        headers=headers,
        json={
            "name": "Already Funded",
            "target_amount_paise": 500_000,
            "saved_paise": 600_000,
            "target_date": "2020-01-01",
            "priority": 1,
        },
    )
    assert g1.status_code == 201
    goal1 = g1.json()["goals"][0]
    assert goal1["is_past_due"] is True
    assert goal1["is_funded"] is True
    assert goal1["over_saved_paise"] == 100_000
    assert goal1["suggested_monthly_paise"] == 0

    # Goal 2 & Goal 3: exceed ₹20,000/mo savings share -> conflict!
    next_year = today_ist.replace(year=today_ist.year + 1).isoformat()
    client.post(
        "/api/v1/plan/goals",
        headers=headers,
        json={
            "name": "Laptop",
            "target_amount_paise": 18_000_000,
            "saved_paise": 0,
            "target_date": next_year,
            "priority": 1,
        },
    )
    g3_res = client.post(
        "/api/v1/plan/goals",
        headers=headers,
        json={
            "name": "Bike",
            "target_amount_paise": 18_000_000,
            "saved_paise": 0,
            "target_date": next_year,
            "priority": 2,
        },
    )
    ov = g3_res.json()
    assert ov["has_allocation_conflict"] is True
    assert ov["shortfall_paise"] > 0
    bike = next(g for g in ov["goals"] if g["name"] == "Bike")
    assert bike["feasible"] is False

    # Edit Goal + 409 conflict on stale expected_version
    upd = client.put(
        f"/api/v1/plan/goals/{bike['id']}",
        headers=headers,
        json={"priority": 1, "expected_version": bike["version"]},
    )
    assert upd.status_code == 200
    stale = client.put(
        f"/api/v1/plan/goals/{bike['id']}",
        headers=headers,
        json={"priority": 3, "expected_version": bike["version"]},
    )
    assert stale.status_code == 409

    # Delete Goal
    del_res = client.delete(f"/api/v1/plan/goals/{bike['id']}", headers=headers)
    assert del_res.status_code == 200
    assert all(g["id"] != bike["id"] for g in del_res.json()["goals"])


def test_emergency_fund_zero_months_needs_plus_recurring_and_409(client: TestClient) -> None:
    headers, _ = _register_and_consent(client, "ef")
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    ist_month = today_ist.strftime("%Y-%m")
    client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": ist_month,
            "monthly_income_paise": 10_000_000,
            "needs_pct": 50,
            "wants_pct": 30,
            "savings_pct": 20,
        },
    )
    client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Rent",
            "category": "Rent & Housing",
            "expected_amount": 10000,
            "frequency": "monthly",
            "due_rule_day": 5,
        },
    )

    ef0 = client.get("/api/v1/plan/emergency-fund", headers=headers).json()
    assert ef0["target_months"] == 6
    assert ef0["needs_paise"] == 5_000_000
    assert ef0["essential_recurring_paise"] == 1_000_000
    assert ef0["essential_monthly_paise"] == 6_000_000
    assert ef0["target_amount_paise"] == 36_000_000

    # Update to 0 months edge case -> target 0, progress 100%, no ZeroDivisionError
    ef_zero = client.put(
        "/api/v1/plan/emergency-fund",
        headers=headers,
        json={"target_months": 0, "saved_paise": 500_000, "expected_version": 0},
    )
    assert ef_zero.status_code == 200
    assert ef_zero.json()["target_amount_paise"] == 0
    assert ef_zero.json()["progress_pct"] == 100.0
    assert ef_zero.json()["over_saved_paise"] == 500_000

    # Stale version -> 409
    stale = client.put(
        "/api/v1/plan/emergency-fund",
        headers=headers,
        json={"target_months": 3, "saved_paise": 500_000, "expected_version": 0},
    )
    assert stale.status_code == 409


def test_goals_cross_user_404(client: TestClient) -> None:
    h_a, _ = _register_and_consent(client, "ga")
    h_b, _ = _register_and_consent(client, "gb")
    g_res = client.post(
        "/api/v1/plan/goals",
        headers=h_a,
        json={
            "name": "A Goal",
            "target_amount_paise": 100_000,
            "saved_paise": 0,
            "target_date": "2027-01-01",
            "priority": 1,
        },
    )
    goal_id = g_res.json()["goals"][0]["id"]
    assert client.put(f"/api/v1/plan/goals/{goal_id}", headers=h_b, json={"name": "Hijack"}).status_code == 404
    assert client.delete(f"/api/v1/plan/goals/{goal_id}", headers=h_b).status_code == 404


@pytest.mark.asyncio
async def test_goals_and_emergency_fund_assistant_tools(client: TestClient) -> None:
    headers, user_id = _register_and_consent(client, "tools")
    assert len(headers) > 0
    p1 = create_deterministic_plan(RouteClass.PERSONAL_FINANCE, "How are my savings goals?")
    assert any(tc.tool_name == "get_goals" for tc in p1.tool_calls)
    p2 = create_deterministic_plan(RouteClass.PERSONAL_FINANCE, "How is my emergency fund?")
    assert any(tc.tool_name == "get_emergency_fund" for tc in p2.tool_calls)

    # Verify end-to-end tool execution via /api/v1/assistant/chat (uses test DB session)
    c_goals = client.post("/api/v1/assistant/chat", headers=headers, json={"question": "How are my savings goals?"})
    assert c_goals.status_code == 200
    assert "goals_count" in c_goals.json().get("facts_used", [])

    c_ef = client.post("/api/v1/assistant/chat", headers=headers, json={"question": "How is my emergency fund?"})
    assert c_ef.status_code == 200
    assert "emergency_target_months" in c_ef.json().get("facts_used", [])
