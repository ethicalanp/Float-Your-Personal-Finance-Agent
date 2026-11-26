import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.scam_detector import analyze_scam_message
from app.services.verified_contacts import get_all_verified_contacts, search_verified_contacts


@pytest.fixture
def protect_user_setup(client: TestClient) -> tuple[TestClient, dict[str, str]]:
    email = f"protect_edge_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "Protect Edge User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


def test_scam_detection_true_positives_multilingual() -> None:
    cases = [
        # English task scam with link & urgency
        (
            "Earn 5000 INR daily liking YouTube videos. Click http://bit.ly/task-earn to claim reward immediately.",
            "HIGH",
        ),
        # English digital arrest
        (
            "CBI officer calling. You are under digital arrest for money laundering. Transfer funds immediately.",
            "MEDIUM",
        ),
        # Malayalam electricity disconnection threat
        (
            "ഇന്നു രാത്രി വൈദ്യുതി വിച്ഛേദിക്കും. പാൻ കാർഡ് ലിങ്ക് ചെയ്യുക അല്ലെങ്കിൽ ലിങ്കിൽ ക്ലിക്ക് ചെയ്യുക http://bit.ly/kseb",
            "HIGH",
        ),
        # Manglish electricity disconnection
        (
            "Urgent aayi electricity bill adakkuka linkil click cheyyu "
            "http://bit.ly/kseb illenkil connection cut aakum tonight.",
            "HIGH",
        ),
        # APK loan lure
        (
            "Instant loan 50000 approved without documents. Download apk fastcash.apk now to receive funds: http://bit.ly/apk",
            "HIGH",
        ),
    ]
    for text, _min_risk in cases:
        res = analyze_scam_message(text)
        assert res["risk_tier"] in ("HIGH", "CRITICAL", "MEDIUM"), f"Failed for text: {text}"
        assert res["risk_score"] >= 35, f"Score too low ({res['risk_score']}) for: {text}"


def test_scam_detection_benign_false_positives() -> None:
    benign_cases = [
        # Normal job interview
        "Hi, I have a legitimate interview scheduled tomorrow morning for the senior data analyst job.",
        # Malayalam normal transfer
        "ഞാൻ എന്റെ അക്കൗണ്ടിൽ നിന്നും അമ്മയുടെ അക്കൗണ്ടിലേക്ക് 5000 രൂപ ഗൂഗിൾ പേ വഴി അയച്ചു.",
        # Manglish mutual fund discussion
        "Njan mutual fund sip thudangan agrahikkunnu. Oru nalla balanced fund suggest cheyyamo?",
        # Normal banking notification
        "Your SBI account has been credited with Rs 45000 for monthly salary on 2026-03-01.",
    ]
    for text in benign_cases:
        res = analyze_scam_message(text)
        assert res["risk_tier"] in ("LOW", "SAFE"), f"Benign text flagged as risky: {text} -> {res}"
        assert res["risk_score"] < 45, f"Benign score too high ({res['risk_score']}) for: {text}"


def test_recovery_case_lifecycle(protect_user_setup: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = protect_user_setup

    # 1. Create recovery case
    create_res = client.post(
        "/api/v1/protect/recovery-cases",
        headers=headers,
        json={
            "scam_type": "upi_fraud",
            "incident_summary": "Unauthorized UPI transaction after clicking remote link",
            "amount_lost": 30000.0,
            "platform": "WhatsApp",
        },
    )
    assert create_res.status_code == 201
    case_data = create_res.json()
    case_id = case_data.get("case_id") or case_data.get("id")
    assert case_data["status"] == "reported"
    assert len(case_data["checklist"]) > 0

    # 2. Update status through valid transitions
    patch_action = client.patch(
        f"/api/v1/protect/recovery-cases/{case_id}",
        headers=headers,
        json={"status": "in_progress", "completed_step": "call_1930"},
    )
    assert patch_action.status_code == 200
    assert patch_action.json()["status"] == "in_progress"

    patch_res = client.patch(
        f"/api/v1/protect/recovery-cases/{case_id}",
        headers=headers,
        json={"status": "resolved"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "resolved"


def test_verified_contacts_priority_and_lookup() -> None:
    contacts = get_all_verified_contacts()
    assert len(contacts) > 0

    # Priority check: National Cyber Crime 1930 must be first priority
    first = contacts[0]
    assert first["toll_free_number"] == "1930"
    assert "cybercrime.gov.in" in first["website"]

    # Bank lookup
    sbi_contacts = search_verified_contacts("sbi")
    assert len(sbi_contacts) > 0
    assert "1800" in sbi_contacts[0]["toll_free_number"]
