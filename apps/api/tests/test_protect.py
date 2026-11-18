import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.services.scam_detector import analyze_scam_message, detect_language


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = create_access_token(
        subject="protect-user-uuid",
        claims={"email": "protect_test@example.com", "full_name": "Protect Tester", "consent_given": True},
    )
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
    en_scam = "URGENT: Your SBI account is suspended! Update KYC immediately by clicking http://bit.ly/sbi-verify or share OTP."
    res_en = analyze_scam_message(en_scam)
    assert res_en["is_scam"] is True
    assert res_en["risk_tier"] in ["HIGH", "CRITICAL"]
    assert any(ind["category"] == "credential_harvesting" for ind in res_en["detected_indicators"])

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
    # 1. Scam Check API
    check_res = client.post(
        "/api/v1/protect/check",
        json={"message": "Urgent: electricity cut aakum. APK install cheyyu http://scam.apk"},
    )
    assert check_res.status_code == 200
    check_id = check_res.json()["check_id"]
    assert check_res.json()["analysis"]["is_scam"] is True

    # 2. Feedback API
    fb_res = client.post(
        "/api/v1/protect/check/feedback",
        json={"check_id": check_id, "is_accurate": True, "notes": "Accurate detection of APK scam"},
    )
    assert fb_res.status_code == 200

    # 3. Submit daily scam sample
    sample_res = client.post(
        "/api/v1/protect/samples",
        json={
            "text": "Electricity cut aakum night 9 pm. Call officer at 9876543210",
            "language": "manglish",
            "is_scam": True,
            "scam_type": "electricity_bill_fraud",
        },
    )
    assert sample_res.status_code == 201

    # 4. Verified contacts search
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

    # 7. Audit Trail API
    audit_res = client.get("/api/v1/protect/audit-trail", headers=auth_headers)
    assert audit_res.status_code == 200
    assert len(audit_res.json()) > 0
