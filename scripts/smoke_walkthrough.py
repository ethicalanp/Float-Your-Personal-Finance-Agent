"""
Real-Backend Smoke Walkthrough (Item 9)
Runs against the real PostgreSQL database in Docker with ENV=local and fake AI provider.
Walks the user flow: signup -> consent -> CSV upload -> home (cash flow) -> protect -> borrow -> assistant.
"""
import os
import sys

# Configure environment for real local postgres & fake AI provider
os.environ["ENV"] = "local"
os.environ["PFA_APP_ENV"] = "development"
os.environ["PFA_AI_PROVIDER"] = "fake"
os.environ["PFA_LLM_PROVIDER"] = "fake"
os.environ["PFA_DATABASE_URL"] = "postgresql+psycopg://float:float_dev_password_change_me@localhost:5432/float"
os.environ["PFA_BORROW_MODEL_PATH"] = "artifacts/synthetic_ml_v2/borrow_model_lightgbm"

import uuid
from fastapi.testclient import TestClient
from app.main import app

def run_smoke():
    client = TestClient(app)
    results = {}
    
    # 1. Health & Capabilities Check
    health_res = client.get("/ready")
    assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
    
    caps_res = client.get("/api/v1/auth/capabilities")
    assert caps_res.status_code == 200
    
    # 2. Signup
    unique_email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
    signup_payload = {
        "email": unique_email,
        "password": "StrongPassword123!",
        "full_name": "Smoke Test User"
    }
    signup_res = client.post("/api/v1/auth/register", json=signup_payload)
    results["signup"] = "PASS" if signup_res.status_code in (200, 201) else f"FAIL ({signup_res.status_code}: {signup_res.text})"
    assert signup_res.status_code in (200, 201), f"Signup failed: {signup_res.text}"
    
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2b. Login validation (valid credentials -> 200, invalid password -> 401)
    bad_login_res = client.post("/api/v1/auth/login", json={"email": unique_email, "password": "WrongPassword999!"})
    assert bad_login_res.status_code == 401, f"Expected 401 on wrong password, got {bad_login_res.status_code}"
    results["login_invalid"] = "PASS"

    good_login_res = client.post("/api/v1/auth/login", json={"email": unique_email, "password": "StrongPassword123!"})
    assert good_login_res.status_code == 200, f"Expected 200 on good login, got {good_login_res.status_code}"
    assert "access_token" in good_login_res.json()
    results["login_valid"] = "PASS"
    
    # 3. Consent
    consent_payload = {
        "terms_accepted": True,
        "privacy_accepted": True,
        "ai_data_processing_consent": True,
    }
    consent_res = client.post("/api/v1/auth/consent", json=consent_payload, headers=headers)
    results["consent"] = "PASS" if consent_res.status_code == 200 else f"FAIL ({consent_res.status_code}: {consent_res.text})"
    assert consent_res.status_code == 200, f"Consent failed: {consent_res.text}"
    
    # 4. Account Creation
    acc_payload = {
        "name": "Smoke Savings",
        "account_type": "savings",
        "institution_name": "State Bank of India",
        "account_number_mask": "****9876",
        "currency": "INR",
        "initial_balance": 10000.0
    }
    acc_res = client.post("/api/v1/plan/accounts", json=acc_payload, headers=headers)
    assert acc_res.status_code in (200, 201), f"Account creation failed: {acc_res.text}"
    account_id = acc_res.json()["id"]
    
    # 5. CSV Statement Upload
    csv_statement = (
        "Date,Description,Amount,Type\n"
        "2026-10-01,Salary Credit,85000,credit\n"
        "2026-10-05,House Rent Transfer,25000,debit\n"
        "2026-10-10,Supermarket Grocery,8500,debit\n"
        "2026-10-15,Electricity Bill,2200,debit\n"
        "2026-11-01,Salary Credit,85000,credit\n"
        "2026-11-05,House Rent Transfer,25000,debit\n"
        "2026-11-12,Dining & Food,4500,debit\n"
    )
    upload_payload = {
        "account_id": account_id,
        "format": "csv",
        "content": csv_statement
    }
    upload_res = client.post("/api/v1/plan/upload-statement", json=upload_payload, headers=headers)
    results["csv_upload"] = "PASS" if upload_res.status_code == 200 and upload_res.json().get("imported_count", 0) > 0 else f"FAIL ({upload_res.status_code}: {upload_res.text})"
    assert upload_res.status_code == 200, f"CSV upload failed: {upload_res.text}"
    
    # 6. Home (Cash Flow Summary)
    flow_res = client.get("/api/v1/plan/cash-flow", headers=headers)
    results["home"] = "PASS" if flow_res.status_code == 200 and flow_res.json().get("total_inflow", 0) > 0 else f"FAIL ({flow_res.status_code}: {flow_res.text})"
    assert flow_res.status_code == 200, f"Cash flow failed: {flow_res.text}"
    
    # 7. Protect (Scam Check)
    scam_payload = {
        "message": "Your electricity bill is overdue. Power disconnected tonight unless you pay at http://bit.ly/kseb-urgent",
        "language_hint": "en"
    }
    protect_res = client.post("/api/v1/protect/check", json=scam_payload, headers=headers)
    results["protect"] = "PASS" if protect_res.status_code == 200 and "analysis" in protect_res.json() else f"FAIL ({protect_res.status_code}: {protect_res.text})"
    assert protect_res.status_code == 200, f"Protect failed: {protect_res.text}"
    
    # 8. Borrow (Readiness Assessment - Requires 200/201 with tier + reasons)
    borrow_payload = {"account_id": account_id}
    borrow_res = client.post("/api/v1/borrow/assess", json=borrow_payload, headers=headers)
    assert borrow_res.status_code == 201, f"Borrow assessment failed (status {borrow_res.status_code}): {borrow_res.text}"
    borrow_data = borrow_res.json()
    assert "readiness_band" in borrow_data and borrow_data["readiness_band"], "Missing readiness tier"
    assert "top_factors" in borrow_data and len(borrow_data["top_factors"]) > 0, "Missing factor reasons"
    results["borrow"] = f"PASS (tier: {borrow_data['readiness_band']}, {len(borrow_data['top_factors'])} factors)"

    # 8b. Borrow 503 Fallback Test (Separate test: unconfigured model must fail gracefully with 503)
    from app.core.config import get_settings
    orig_path = get_settings().borrow_model_path
    try:
        get_settings().borrow_model_path = "non_existent_model_dir"
        fallback_res = client.post("/api/v1/borrow/assess", json=borrow_payload, headers=headers)
        assert fallback_res.status_code == 503, f"Expected 503 for unconfigured borrow model, got {fallback_res.status_code}"
        results["borrow_503_fallback"] = "PASS (503 Service Unavailable on unconfigured model)"
    finally:
        get_settings().borrow_model_path = orig_path

    # 9. Assistant (Knowledge RAG / Chat)
    assistant_payload = {
        "question": "What is the 3-day zero liability rule for unauthorized banking transactions?",
        "language_hint": "en"
    }
    assistant_res = client.post("/api/v1/assistant/knowledge", json=assistant_payload, headers=headers)
    results["assistant"] = "PASS" if assistant_res.status_code == 200 and "answer" in assistant_res.json() else f"FAIL ({assistant_res.status_code}: {assistant_res.text})"
    assert assistant_res.status_code == 200, f"Assistant failed: {assistant_res.text}"

    # 10. Profile & Settings (GET/PATCH /me, sessions, DPDP export, delete + cancel)
    me_res = client.get("/api/v1/me", headers=headers)
    assert me_res.status_code == 200, f"GET /me failed: {me_res.text}"
    patch_res = client.patch(
        "/api/v1/me",
        json={"full_name": "Smoke User Updated", "preferred_language": "en", "locale": "en-IN"},
        headers=headers,
    )
    assert patch_res.status_code == 200, f"PATCH /me failed: {patch_res.text}"
    assert patch_res.json()["full_name"] == "Smoke User Updated"

    sess_res = client.get("/api/v1/auth/sessions", headers=headers)
    assert sess_res.status_code == 200, f"GET /auth/sessions failed: {sess_res.text}"

    exp_res = client.post("/api/v1/me/export", headers=headers)
    assert exp_res.status_code == 200 and "profile" in exp_res.json(), f"POST /me/export failed: {exp_res.text}"

    del_res = client.delete("/api/v1/me", headers=headers)
    assert del_res.status_code == 200 and del_res.json()["status"] == "deletion_scheduled", f"DELETE /me failed: {del_res.text}"

    cancel_res = client.post("/api/v1/me/delete/cancel", headers=headers)
    assert cancel_res.status_code == 200 and cancel_res.json()["deletion_scheduled_for"] is None, f"POST /me/delete/cancel failed: {cancel_res.text}"
    results["profile_and_settings"] = "PASS"

    # 11. Budget Plan -> Edit Split -> Add Recurring -> Upload CSV -> Tagged Expected -> Float.ai Budget Query
    from datetime import datetime
    from zoneinfo import ZoneInfo

    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    ist_month = ist_today.strftime("%Y-%m")

    b1 = client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={"month": ist_month, "monthly_income_paise": 10_000_000, "needs_pct": 50, "wants_pct": 30, "savings_pct": 20},
    )
    assert b1.status_code == 200, f"Budget create failed: {b1.text}"
    results["budget_set_income"] = "PASS"

    b2 = client.put(
        "/api/v1/plan/budget",
        headers=headers,
        json={
            "month": ist_month,
            "monthly_income_paise": 10_000_000,
            "needs_pct": 60,
            "wants_pct": 20,
            "savings_pct": 20,
            "expected_version": 1,
        },
    )
    assert b2.status_code == 200 and b2.json()["needs_paise"] == 6_000_000, f"Budget split edit failed: {b2.text}"
    results["budget_edit_split"] = "PASS"

    rec_add = client.post(
        "/api/v1/recurring/commitments",
        headers=headers,
        json={
            "name": "Netflix",
            "category": "Subscriptions",
            "expected_amount": 649,
            "frequency": "monthly",
            "due_rule_day": ist_today.day,
            "merchant": "Netflix",
            "merchant_keywords": ["netflix"],
            "start_date": ist_today.replace(day=1).isoformat(),
        },
    )
    assert rec_add.status_code == 201, f"Add recurring failed: {rec_add.text}"
    results["recurring_add"] = "PASS"

    rec_csv = f"Date,Description,Amount,Type\n{ist_today.isoformat()},Netflix India Subscription,649,debit\n"
    rec_up = client.post(
        "/api/v1/plan/upload-statement",
        headers=headers,
        json={"account_id": account_id, "format": "csv", "content": rec_csv},
    )
    assert rec_up.status_code == 200, f"Recurring CSV upload failed: {rec_up.text}"

    txs = client.get("/api/v1/plan/transactions", headers=headers).json()
    matched_tx = [t for t in txs if "netflix" in t["description"].lower()]
    assert matched_tx and matched_tx[0]["is_recurring"] is True, f"Recurring tx not tagged expected: {txs}"
    results["recurring_tagged_expected"] = "PASS"

    chat_res = client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={"question": "how is my budget this month?"},
    )
    assert chat_res.status_code == 200, f"Float.ai chat failed: {chat_res.text}"
    chat_body = chat_res.json()
    assert chat_body["status"] in ("success", "insufficient_evidence", "degraded_fallback"), f"Unexpected chat status: {chat_body}"
    facts_used = set(chat_body.get("facts_used", []))
    assert {"budget_needs_inr", "budget_wants_inr", "budget_savings_inr"}.issubset(facts_used), (
        f"Expected get_budget_plan facts, got {facts_used}"
    )
    plan_data = b2.json()
    answer_norm = chat_body["answer"].replace(",", "")
    for paise_key in ("needs_paise", "wants_paise", "savings_paise"):
        inr_int = str(plan_data[paise_key] // 100)
        assert inr_int in answer_norm, (
            f"Expected {paise_key} ({inr_int} INR) in Float.ai answer: {chat_body['answer']}"
        )
    results["float_ai_budget_query"] = f"PASS (status={chat_body['status']}, facts={chat_body.get('facts_used', [])})"

    print("\n=== SMOKE WALKTHROUGH RESULTS ===")
    for step, outcome in results.items():
        print(f"  {step}: {outcome}")

if __name__ == "__main__":
    run_smoke()
