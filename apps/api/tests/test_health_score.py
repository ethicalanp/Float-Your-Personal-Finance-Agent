from datetime import UTC, datetime

from fastapi.testclient import TestClient


def _register_and_consent(client: TestClient, tag: str) -> dict[str, str]:
    email = f"hs_{tag}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"Health {tag}"},
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
    return headers


def test_health_score_no_data_never_zeros(client: TestClient) -> None:
    headers = _register_and_consent(client, "nodata")
    res = client.get("/api/v1/plan/health-score", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["formula_version"] == "v1.0.0"
    assert body["overall_score"] is None
    assert body["band"] == "insufficient_data"
    assert body["available_components"] == 0
    assert len(body["components"]) == 6
    assert all(c["status"] == "insufficient_data" and c["score"] is None for c in body["components"])
    assert body["best_next_action"]["pillar"] == "Plan"


def test_health_score_one_component_only_and_history_delta(client: TestClient) -> None:
    headers = _register_and_consent(client, "onecomp")

    # 1. Set insurance = False (score 25)
    r1 = client.put(
        "/api/v1/plan/health-score/insurance",
        headers=headers,
        json={"has_essential_insurance": False},
    )
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["available_components"] == 1
    assert b1["overall_score"] == 25
    assert b1["confidence"] == "low"
    assert b1["band"] == "needs_attention"

    # 2. Update insurance = True (score 100 -> delta +75)
    r2 = client.put(
        "/api/v1/plan/health-score/insurance",
        headers=headers,
        json={"has_essential_insurance": True},
    )
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["overall_score"] == 100
    assert b2["delta_from_previous"] == 75
    assert len(b2["history"]) >= 2

    # 3. Formula version change suppresses delta and sets version_changed=True
    r3 = client.get("/api/v1/plan/health-score?formula_version=v1.1.0", headers=headers)
    assert r3.status_code == 200
    b3 = r3.json()
    assert b3["formula_version"] == "v1.1.0"
    assert b3["version_changed"] is True
    assert b3["delta_from_previous"] is None


def test_health_score_zero_income_and_full_breakdown(client: TestClient) -> None:
    headers = _register_and_consent(client, "zeroinc")
    acc = client.post(
        "/api/v1/plan/accounts",
        headers=headers,
        json={
            "name": "HDFC Savings",
            "account_type": "savings",
            "institution_name": "HDFC",
            "account_number_mask": "****9999",
            "initial_balance": 120000,
        },
    ).json()
    today = datetime.now(UTC).date().isoformat()
    # Zero income (debit only) -> savings_rate, dti, subscriptions_share must be insufficient_data
    client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={
            "account_id": acc["id"],
            "format": "csv",
            "content": f"Date,Description,Amount,Type\n{today},Groceries,10000,debit\n",
        },
    )
    r_zero = client.get("/api/v1/plan/health-score", headers=headers).json()
    comps_zero = {c["key"]: c for c in r_zero["components"]}
    assert comps_zero["savings_rate"]["status"] == "insufficient_data"
    assert comps_zero["debt_to_income"]["status"] == "insufficient_data"
    assert comps_zero["subscriptions_share"]["status"] == "insufficient_data"
    assert comps_zero["emergency_fund_months"]["status"] == "available"

    # Now add income + budget + recurring + insurance
    client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={
            "account_id": acc["id"],
            "format": "csv",
            "content": f"Date,Description,Amount,Type\n{today},Salary Credit,100000,credit\n",
        },
    )
    month = today[:7]
    client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={"month": month, "monthly_income_paise": 10_000_000, "needs_pct": 50, "wants_pct": 30, "savings_pct": 20},
    )
    client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Car EMI",
            "category": "EMI",
            "expected_amount": 10000,
            "frequency": "monthly",
            "due_rule_day": 5,
        },
    )
    client.put(
        "/api/v1/plan/health-score/insurance",
        headers=headers,
        json={"has_essential_insurance": True},
    )
    r_full = client.get("/api/v1/plan/health-score", headers=headers).json()
    assert r_full["available_components"] == 6
    assert r_full["overall_score"] is not None
    assert r_full["overall_score"] >= 80
    assert r_full["band"] == "strong"
    assert "educational" in r_full["disclaimer"].lower()
    pillars = {s["pillar"] for s in r_full["float_path"]}
    assert {"Protect", "Borrow-ready"}.issubset(pillars)


def test_health_score_cross_user_isolation(client: TestClient) -> None:
    h_a = _register_and_consent(client, "usera")
    h_b = _register_and_consent(client, "userb")
    client.put("/api/v1/plan/health-score/insurance", headers=h_a, json={"has_essential_insurance": True})

    b_res = client.get("/api/v1/plan/health-score", headers=h_b).json()
    assert b_res["has_essential_insurance"] is None
    assert b_res["available_components"] == 0
    assert b_res["history"] == []
