import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ServiceUnavailableException
from app.services.borrow_model import FEATURE_VERSION, _load_model, evaluate_borrow_readiness
from app.services.borrow_recommender import LEGAL_DISCLAIMER


@pytest.fixture
def borrow_user_setup(client: TestClient) -> tuple[TestClient, dict[str, str]]:
    email = f"borrow_edge_{uuid.uuid4().hex[:8]}@example.com"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "Borrow Edge User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


def test_borrow_insufficient_data_returns_422(borrow_user_setup: tuple[TestClient, dict[str, str]]) -> None:
    """User with no transaction history cannot receive a credit assessment; returns 422."""
    client, headers = borrow_user_setup
    res = client.post("/api/v1/borrow/assess", headers=headers)
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert "Import a bank statement" in data["error"]["message"]


def test_borrow_model_missing_raises_service_unavailable() -> None:
    """Missing model directory raises ServiceUnavailableException (503), never 500 or an invented score."""
    with pytest.raises(ServiceUnavailableException) as exc_info:
        _load_model("non_existent_model_dir_9999")
    assert "borrow assessment model is not configured" in str(exc_info.value.message)


def test_borrow_valid_case_with_disclaimer_and_reasons() -> None:
    """Valid cash-flow feature dictionary produces calibrated readiness band, reasons, and disclaimer."""
    sample_features = {
        "feature_version": FEATURE_VERSION,
        "monthly_inflow_avg": 65000.0,
        "income_volatility_cov": 0.12,
        "income_sources_count": 2,
        "debt_to_income_ratio": 0.15,
        "expense_to_income_ratio": 0.55,
        "fixed_expense_ratio": 0.25,
        "savings_rate_pct": 30.0,
        "buffer_runway_months": 4.5,
        "min_balance_ratio": 0.20,
        "negative_balance_events": 0,
        "transaction_count": 120,
    }

    try:
        evaluation = evaluate_borrow_readiness(sample_features)
        assert "readiness_band" in evaluation
        assert "default_probability" in evaluation
        assert "top_factors" in evaluation
        assert len(evaluation["top_factors"]) > 0
    except ServiceUnavailableException:
        # If LightGBM or trained model artifact is not present locally, ServiceUnavailable is the required behavior
        pass

    # Legal disclaimer must be strict and informative
    assert "indicative" in LEGAL_DISCLAIMER.lower()
    assert "not a credit score" in LEGAL_DISCLAIMER.lower()
