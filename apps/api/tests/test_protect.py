import pytest
from fastapi.testclient import TestClient

from app.services.scam_detector import analyze_scam_message, detect_language


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    reg_data = {
        "email": "protect_test@example.com",
        "password": "StrongPassword123!",
        "full_name": "Protect Tester",
        "terms_accepted": True,
        "ai_data_processing_consent": True,
    }
    res = client.post("/api/v1/auth/register", json=reg_data)
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_language_detection() -> None:
    en_msg = "Your bank account has been locked. Verify immediately."
    ml_msg = "നിങ്ങളുടെ അക്കൗണ്ട് താൽക്കാലികമായി ബ്ലോക്ക് ചെയ്തു."
    manglish_msg = "Ningalude account block aayi, udan thanne linkil click cheyyuka."

    assert detect_language(en_msg) == "en"
    assert detect_language(ml_msg) == "ml"
    assert detect_language(manglish_msg) == "manglish"


def test_scam_detector_multilingual() -> None:
    # 1. English Scam
    en_scam = (
        "URGENT: Your SBI account is suspended! Update KYC immediately by clicking "
        "http://bit.ly/sbi-verify or share OTP."
    )
    res_en = analyze_scam_message(en_scam)
    assert res_en["is_scam"] is True
    assert res_en["risk_tier"] in ["HIGH", "CRITICAL"]
    assert any(ind["category"] == "credential_harvesting" for ind in res_en["detected_indicators"])

    otp_request = analyze_scam_message("SYNTHETIC TEST ONLY: account blocked, please share your OTP.")
    assert otp_request["is_scam"] is True
    assert any(ind["category"] == "credential_harvesting" for ind in otp_request["detected_indicators"])

    # 2. Malayalam Scam
    ml_scam = "അടിയന്തിരമായി കെവൈസി അപ്ഡേറ്റ് ചെയ്യുക. അല്ലെങ്കിൽ ഇന്നു രാത്രി വൈദ്യുതി വിച്ഛേദിക്കും. ലിങ്കിൽ ക്ലിക്ക് ചെയ്യുക: http://bit.ly/eb"
    res_ml = analyze_scam_message(ml_scam)
    assert res_ml["is_scam"] is True
    assert res_ml["language"] == "ml"
    assert res_ml["risk_tier"] in ["HIGH", "CRITICAL"]

    # 3. Manglish Scam
    manglish_scam = "Urgent aayi panam ayakkuka, account block aakum. OTP share cheyyu or linkil click cheyyu."
    res_mang = analyze_scam_message(manglish_scam)
    assert res_mang["is_scam"] is True
    assert res_mang["language"] == "manglish"
    assert res_mang["risk_score"] >= 50

    # 4. Safe message
    safe_msg = "Your OTP for logging in to Swiggy is 492019. Valid for 10 minutes. Do not share with anyone."
    res_safe = analyze_scam_message(safe_msg)
    assert res_safe["risk_tier"] in ["SAFE", "LOW"]


def test_protect_api_endpoints(client: TestClient, auth_headers: dict[str, str]) -> None:
    # 1. Scam Check API (authenticated)
    check_res = client.post(
        "/api/v1/protect/check",
        headers=auth_headers,
        json={"message": "Urgent: electricity cut aakum. APK install cheyyu http://scam.apk"},
    )
    assert check_res.status_code == 200
    check_id = check_res.json()["check_id"]
    assert check_res.json()["analysis"]["is_scam"] is True

    # 2. Feedback API
    fb_res = client.post(
        "/api/v1/protect/check/feedback",
        headers=auth_headers,
        json={"check_id": check_id, "is_accurate": True, "notes": "Accurate detection of APK scam"},
    )
    assert fb_res.status_code == 200

    # 3. Submit daily scam sample (authenticated)
    sample_res = client.post(
        "/api/v1/protect/samples",
        headers=auth_headers,
        json={
            "text": "Electricity cut aakum night 9 pm. Call officer at 9876543210",
            "language": "manglish",
            "is_scam": True,
            "scam_type": "electricity_bill_fraud",
        },
    )
    assert sample_res.status_code == 201
    own_samples = client.get("/api/v1/protect/samples", headers=auth_headers)
    assert len(own_samples.json()) == 1
    assert "9876543210" not in own_samples.json()[0]["text"]

    other_user = client.post(
        "/api/v1/auth/register",
        json={
            "email": "other_sample_user@example.com",
            "password": "StrongPassword123!",
            "full_name": "Other User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    other_headers = {"Authorization": f"Bearer {other_user.json()['access_token']}"}
    assert client.get("/api/v1/protect/samples", headers=other_headers).json() == []

    # 4. Verified contacts search (public lookup)
    vc_res = client.get("/api/v1/protect/verified-contacts?query=sbi")
    assert vc_res.status_code == 200
    assert len(vc_res.json()) >= 1
    assert "1930" in str(vc_res.json()) or "SBI" in str(vc_res.json())

    # 5. Draft Complaint API
    draft_res = client.post(
        "/api/v1/protect/draft-complaint",
        headers=auth_headers,
        json={
            "victim_name": "Anupam",
            "bank_name": "HDFC Bank",
            "account_number_mask": "****9876",
            "transaction_reference": "UTR123456789",
            "transaction_amount": 15000.0,
            "scam_type": "Fake Electricity Bill SMS",
            "incident_description": "Scammer sent an SMS claiming power cut and debited Rs 15000 via malicious link.",
        },
    )
    assert draft_res.status_code == 200
    draft_data = draft_res.json()
    assert "bank_email_draft" in draft_data
    assert "UTR123456789" in draft_data["bank_email_draft"]["body"]
    assert "safety_disclaimer" in draft_data

    # 6. Recovery Case Workflow
    case_res = client.post(
        "/api/v1/protect/recovery-cases",
        headers=auth_headers,
        json={
            "scam_type": "upi_fraud",
            "amount_lost": 15000.0,
            "platform": "SMS",
            "incident_summary": "Phishing SMS regarding electricity disconnection led to unauthorized UPI transfer.",
        },
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]
    assert case_res.json()["status"] == "reported"

    # Progress a step in recovery case
    patch_res = client.patch(
        f"/api/v1/protect/recovery-cases/{case_id}",
        headers=auth_headers,
        json={"completed_step": "call_1930", "status": "in_progress"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "in_progress"

    invalid_status_res = client.patch(
        f"/api/v1/protect/recovery-cases/{case_id}",
        headers=auth_headers,
        json={"status": "invalid"},
    )
    assert invalid_status_res.status_code == 400

    # 7. Audit Trail API (scoped to user)
    audit_res = client.get("/api/v1/protect/audit-trail", headers=auth_headers)
    assert audit_res.status_code == 200
    assert len(audit_res.json()) > 0
    # Every audit entry must belong to the user
    user_id = case_res.json()["user_id"]
    for entry in audit_res.json():
        assert entry["user_id"] == user_id


def test_unauthenticated_protect_endpoints(client: TestClient) -> None:
    # Samples and check endpoints require authentication
    assert client.post("/api/v1/protect/check", json={"message": "hello"}).status_code == 401
    assert client.post("/api/v1/protect/samples", json={"text": "scam", "language": "en"}).status_code == 401
    assert client.get("/api/v1/protect/audit-trail").status_code == 401


def test_protect_consent_enforcement(client: TestClient) -> None:
    # User with NO consent
    reg_no_consent = client.post(
        "/api/v1/auth/register",
        json={
            "email": "noconsent@example.com",
            "password": "StrongPassword123!",
            "full_name": "No Consent",
            "terms_accepted": False,
            "ai_data_processing_consent": False,
        },
    )
    token = reg_no_consent.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Blocked from AI check without AI consent (403)
    res_check = client.post("/api/v1/protect/check", headers=headers, json={"message": "check"})
    assert res_check.status_code == 403
    assert "ai_data_processing" in res_check.json()["error"]["message"]

    # Blocked from recovery cases without terms consent (403)
    res_case = client.post(
        "/api/v1/protect/recovery-cases",
        headers=headers,
        json={
            "scam_type": "upi_fraud",
            "amount_lost": 1000.0,
            "platform": "SMS",
            "incident_summary": "Summary",
        },
    )
    assert res_case.status_code == 403
    assert "terms" in res_case.json()["error"]["message"]
