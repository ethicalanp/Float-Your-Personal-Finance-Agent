import csv
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.errors import ServiceUnavailableException
from app.models.enums import ReadinessBand
from app.services.borrow_features import (
    FEATURE_COLUMNS,
    FEATURE_VERSION,
    _is_earned_income,
    _is_expense,
)
from app.services.borrow_model import evaluate_borrow_readiness
from app.services.borrow_recommender import (
    LEGAL_DISCLAIMER,
    generate_borrow_recommendations,
)
from scripts.train_borrow_model import AS_OF_COLUMN, _temporal_embargo_split, train_model


@pytest.fixture
def user_with_consent(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "borrow_consent@example.com",
            "password": "StrongPassword123!",
            "full_name": "Borrow Consented User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def user_without_ai_consent(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "borrow_no_consent@example.com",
            "password": "StrongPassword123!",
            "full_name": "No AI Consent User",
            "terms_accepted": True,
            "ai_data_processing_consent": False,
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _write_training_csv(csv_path: Path, row_count: int = 600) -> None:
    headers = ["user_id", "as_of_date", "target_default", *FEATURE_COLUMNS]
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        start = date(2020, 1, 1)
        for index in range(row_count):
            is_default = index % 2
            writer.writerow(
                {
                    "user_id": f"user-{index}",
                    "as_of_date": (start + timedelta(days=index)).isoformat(),
                    "target_default": is_default,
                    "monthly_inflow_avg": 30000 + index % 17000,
                    "income_volatility_cov": 0.8 if is_default else 0.15,
                    "income_sources_count": 1 if is_default else 2,
                    "debt_to_income_ratio": 0.55 if is_default else 0.12,
                    "expense_to_income_ratio": 0.92 if is_default else 0.50,
                    "fixed_expense_ratio": 0.60 if is_default else 0.20,
                    "savings_rate_pct": -10 if is_default else 25,
                    "buffer_runway_months": 0.3 if is_default else 4.0,
                    "min_balance_ratio": "",
                    "negative_balance_events": "",
                }
            )


def test_income_feature_excludes_refunds_and_transfers() -> None:
    assert _is_earned_income("Income & Salary", "Monthly salary", "Employer")
    assert not _is_earned_income("Income & Salary", "Cashback credit", "Merchant")
    assert not _is_earned_income("Transfers", "Received from own account", "Bank")
    assert _is_expense("Rent & Housing", "Monthly rent")
    assert not _is_expense("Transfers", "Transfer to own account")
    assert not _is_expense("Other", "Credit card bill payment")


def test_temporal_splits_group_dates_and_apply_all_embargoes() -> None:
    horizon_days = 90
    rows = [
        {
            AS_OF_COLUMN: date(2020, 1, 1) + timedelta(days=index),
            "target_default": index % 2,
            "features": [],
        }
        for index in range(1000)
    ]

    fit, early_stopping, calibration, test = _temporal_embargo_split(rows, horizon_days)
    partitions = [fit, early_stopping, calibration, test]

    for left, right in zip(partitions, partitions[1:], strict=False):
        left_dates = {row[AS_OF_COLUMN] for row in left}
        right_dates = {row[AS_OF_COLUMN] for row in right}
        assert left_dates.isdisjoint(right_dates)
        assert (min(right_dates) - max(left_dates)).days > horizon_days


def test_training_and_tree_shap_inference_round_trip(tmp_path: Path) -> None:
    try:
        import lightgbm
        import shap
    except (ImportError, OSError) as exc:
        pytest.skip(f"LightGBM/SHAP native runtime unavailable: {exc}")

    del lightgbm, shap
    training_csv = tmp_path / "training.csv"
    artifact_dir = tmp_path / "artifact"
    _write_training_csv(training_csv)

    metadata = train_model(
        training_csv,
        artifact_dir,
        data_source="synthetic unit-test fixture",
        label_horizon_days=90,
        model_version="test",
        num_boost_round=30,
    )
    result = evaluate_borrow_readiness(
        {
            "feature_version": FEATURE_VERSION,
            "monthly_inflow_avg": 30000,
            "income_volatility_cov": 0.8,
            "income_sources_count": 1,
            "debt_to_income_ratio": 0.55,
            "expense_to_income_ratio": 0.92,
            "fixed_expense_ratio": 0.60,
            "savings_rate_pct": -10,
            "buffer_runway_months": 0.3,
            "min_balance_ratio": None,
            "negative_balance_events": None,
        },
        model_dir=artifact_dir,
    )

    assert metadata["model_version"] == "lightgbm_cashflow_test"
    assert 0.0 <= result["default_probability"] <= 1.0
    assert len(result["negative_factors"]) <= 3
    assert all(factor["direction"] == "negative" for factor in result["negative_factors"])


def test_training_rejects_repeated_users_to_prevent_split_leakage(tmp_path: Path) -> None:
    training_csv = tmp_path / "training.csv"
    _write_training_csv(training_csv, row_count=100)
    with training_csv.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    rows[1]["user_id"] = rows[0]["user_id"]
    with training_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="multiple snapshots"):
        train_model(
            training_csv,
            tmp_path / "artifact",
            data_source="test",
            label_horizon_days=90,
            model_version="test",
            num_boost_round=10,
        )


def test_inference_fails_clearly_without_a_trained_artifact(tmp_path: Path) -> None:
    with pytest.raises(ServiceUnavailableException, match="model is not configured"):
        evaluate_borrow_readiness(
            {"feature_version": FEATURE_VERSION},
            model_dir=tmp_path / "missing-artifact",
        )


def test_empty_history_returns_clean_import_prompt(
    client: TestClient,
    user_with_consent: dict[str, str],
) -> None:
    response = client.post("/api/v1/borrow/assess", headers=user_with_consent)

    assert response.status_code == 422
    assert "Import a bank statement" in response.json()["error"]["message"]


def test_borrow_consent_enforcement(
    client: TestClient,
    user_without_ai_consent: dict[str, str],
) -> None:
    response = client.post("/api/v1/borrow/assess", headers=user_without_ai_consent)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert "ai_data_processing" in response.json()["error"]["message"]


def test_borrow_recommendations_follow_adverse_features() -> None:
    recommendations = generate_borrow_recommendations(
        ReadinessBand.LOW,
        [
            {"feature": "buffer_runway_months"},
            {"feature": "expense_to_income_ratio"},
            {"feature": "income_volatility_cov"},
        ],
        {
            "buffer_runway_months": 0.4,
            "expense_to_income_ratio": 0.9,
            "income_volatility_cov": 0.8,
        },
    )

    assert len(recommendations) == 3
    assert any("liquidity" in item["title"].lower() for item in recommendations)
    assert any("income" in item["title"].lower() for item in recommendations)


def test_assessment_api_persists_model_result_and_audit(
    client: TestClient,
    user_with_consent: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_response = client.post(
        "/api/v1/plan/accounts",
        headers=user_with_consent,
        json={
            "name": "Salary account",
            "account_type": "savings",
            "institution_name": "Test Bank",
            "account_number_mask": "****1234",
            "initial_balance": 1000,
        },
    )
    account_id = account_response.json()["id"]
    statement = (
        "Date,Narration,Withdrawal,Deposit\n"
        "2026-01-01,SALARY EMPLOYER,,1000\n"
        "2026-01-02,RENT,200,\n"
        "2026-02-01,SALARY EMPLOYER,,2000\n"
        "2026-02-02,RENT,400,\n"
    )
    upload_response = client.post(
        "/api/v1/plan/upload-statement",
        headers=user_with_consent,
        json={"account_id": account_id, "format": "csv", "content": statement},
    )
    assert upload_response.status_code == 200

    monkeypatch.setattr(
        "app.api.v1.borrow.evaluate_borrow_readiness",
        lambda features: {
            "model_version": "test-model",
            "feature_version": FEATURE_VERSION,
            "default_probability": 0.2,
            "readiness_band": ReadinessBand.GOOD,
            "top_factors": [],
            "positive_factors": [],
            "negative_factors": [],
        },
    )
    assessment_response = client.post("/api/v1/borrow/assess", headers=user_with_consent)

    assert assessment_response.status_code == 201
    result = assessment_response.json()
    assert result["feature_version"] == FEATURE_VERSION
    assert result["model_version"] == "test-model"
    assert result["input_features"]["transaction_count"] == 4
    assert result["input_features"]["observed_month_count"] == 2
    assert result["input_features"]["monthly_inflow_avg"] == 1500
    assert result["input_features"]["income_volatility_cov"] == pytest.approx(1 / 3, abs=0.0001)
    assert result["input_features"]["expense_to_income_ratio"] == pytest.approx(0.2)
    assert "SALARY EMPLOYER" not in str(result["input_features"])
    assert result["input_features"]["min_balance_ratio"] is None
    assert result["input_features"]["negative_balance_events"] is None
    assert result["legal_disclaimer"] == LEGAL_DISCLAIMER

    assert client.get("/api/v1/borrow/latest", headers=user_with_consent).json()["id"] == result["id"]
    assert len(client.get("/api/v1/borrow/history", headers=user_with_consent).json()) == 1
