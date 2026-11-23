from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.scam_classifier import HybridScamDetector, ScamClassifier
from scripts.evaluate_borrow_fairness_shap import (
    ADVERSE_REASON_MAP,
    compute_fairness_metrics,
)
from scripts.train_home_credit import (
    SENTINEL_DAYS_EMPLOYED,
    engineer_financial_features,
    find_optimal_threshold,
    safe_divide,
    train_home_credit,
)
from scripts.train_scam_transformer import run_transformer_experiment


def test_safe_divide_handles_zero_and_infinite() -> None:
    num = pd.Series([10.0, 20.0, 30.0])
    denom = pd.Series([2.0, 0.0, 5.0])
    res = safe_divide(num, denom)
    assert res[0] == 5.0
    assert np.isnan(res[1])
    assert res[2] == 6.0


def test_home_credit_financial_feature_engineering() -> None:
    raw_data = pd.DataFrame({
        "AMT_CREDIT": [100000.0, 50000.0],
        "AMT_INCOME_TOTAL": [50000.0, 25000.0],
        "AMT_ANNUITY": [10000.0, 5000.0],
        "AMT_GOODS_PRICE": [90000.0, 45000.0],
        "CNT_FAM_MEMBERS": [2, 1],
        "DAYS_EMPLOYED": [SENTINEL_DAYS_EMPLOYED, -1500],
        "DAYS_BIRTH": [-10000, -12000],
    })
    fe = engineer_financial_features(raw_data)

    assert np.isnan(fe.loc[0, "DAYS_EMPLOYED"])
    assert fe.loc[1, "DAYS_EMPLOYED"] == -1500
    assert fe.loc[0, "CREDIT_INCOME_RATIO"] == 2.0
    assert fe.loc[0, "ANNUITY_INCOME_RATIO"] == 0.2
    assert fe.loc[0, "ANNUITY_CREDIT_RATIO"] == 0.1
    assert fe.loc[0, "GOODS_CREDIT_RATIO"] == 0.9
    assert fe.loc[0, "INCOME_PER_PERSON"] == 25000.0
    assert pytest.approx(fe.loc[1, "EMPLOYED_TO_AGE_RATIO"]) == 1500 / 12000


def test_optimal_threshold_selection() -> None:
    y_val = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    y_val_proba = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    thresh, prec, rec, f1 = find_optimal_threshold(y_val, y_val_proba)

    assert 0.4 < thresh <= 0.6
    assert prec == pytest.approx(1.0)
    assert rec == pytest.approx(1.0)
    assert f1 == pytest.approx(1.0)


def test_home_credit_training_requires_provenance_before_reading_data(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source and terms reference are required"):
        train_home_credit(
            data_path=tmp_path / "not-present.csv",
            output_dir=tmp_path / "artifacts",
            data_source=" ",
            terms_reference="",
        )

    assert not (tmp_path / "artifacts").exists()


def test_fairness_metrics_computation() -> None:
    df = pd.DataFrame({
        "CODE_GENDER": ["F"] * 50 + ["M"] * 50,
    })
    # Scenario: balanced approval
    y_true = np.array([0] * 40 + [1] * 10 + [0] * 40 + [1] * 10)
    y_pred = np.array([0] * 38 + [1] * 12 + [0] * 37 + [1] * 13)

    metrics = compute_fairness_metrics(df, y_true, y_pred, "CODE_GENDER")
    assert "groups" in metrics
    assert "F" in metrics["groups"]
    assert "M" in metrics["groups"]
    assert metrics["disparate_impact_ratio"] > 0.80
    assert len(metrics["disparate_impact_ratio_ci95"]) == 2
    assert len(metrics["tpr_max_disparity_ci95"]) == 2
    assert len(metrics["fpr_max_disparity_ci95"]) == 2
    assert len(metrics["groups"]["F"]["approval_rate_ci95"]) == 2
    assert metrics["passes_four_fifths_rule"] is not True or metrics["disparate_impact_ratio_ci95"][0] >= 0.80


def test_fairness_metrics_do_not_pass_without_two_adequate_groups() -> None:
    df = pd.DataFrame({"AGE_GROUP": ["<30"] * 10 + ["30-50"] * 10})
    y_true = np.array([0, 1] * 10)
    y_pred = np.array([0, 1] * 10)

    metrics = compute_fairness_metrics(df, y_true, y_pred, "AGE_GROUP")

    assert metrics["disparate_impact_ratio"] is None
    assert metrics["passes_four_fifths_rule"] is None
    assert metrics["tpr_max_disparity"] is None
    assert metrics["disparate_impact_ratio_ci95"] is None


def test_adverse_reason_mapping_completeness() -> None:
    assert "CREDIT_INCOME_RATIO" in ADVERSE_REASON_MAP
    assert "ANNUITY_INCOME_RATIO" in ADVERSE_REASON_MAP
    assert "DAYS_EMPLOYED" in ADVERSE_REASON_MAP


def test_scam_classifier_train_and_inference(tmp_path: Path) -> None:
    train_texts = [
        "Urgent: your account will be blocked. Click link to update KYC immediately.",
        "Innu rathri electricity cut aakum. Udan thanne bill adakkuka.",
        "Lottery 25 lakh roopa kittiyirikkunnu. Registration fee ayakkuka.",
        "Your monthly salary of INR 50,000 has been credited to account xx123.",
        "Hi friend, let's catch up tomorrow for lunch at Infopark.",
        "Swiggy delivery completed successfully. Enjoy your meal.",
    ]
    train_labels = [1, 1, 1, 0, 0, 0]

    clf = ScamClassifier()
    res = clf.train(train_texts, train_labels)
    assert res["training_samples"] == 6

    # Test scam detection on unseen test text
    scam_test = "Electricity cut tonight, send money immediately to avoid block."
    ham_test = "Your bank balance statement for October is attached."

    prob_scam = clf.predict_proba(scam_test)
    prob_ham = clf.predict_proba(ham_test)
    assert prob_scam > prob_ham

    # Test persistence
    save_path = tmp_path / "model.joblib"
    clf.save(save_path)
    assert save_path.is_file()

    loaded_clf = ScamClassifier.load(save_path)
    assert loaded_clf.is_fitted
    assert loaded_clf.predict_proba(scam_test) == pytest.approx(prob_scam, abs=1e-4)


def test_unfitted_scam_classifier_does_not_return_a_clean_probability() -> None:
    classifier = ScamClassifier()

    with pytest.raises(RuntimeError, match="not fitted"):
        classifier.predict_proba("A message that has not been evaluated.")


def test_hybrid_scam_detector_fusion() -> None:
    train_texts = [
        "Urgent: your account will be blocked. Click link to update KYC immediately.",
        "Lottery winner! Send processing fee now.",
        "Your monthly salary has been credited.",
        "Let's meet for dinner tonight.",
    ]
    train_labels = [1, 1, 0, 0]
    clf = ScamClassifier()
    clf.train(train_texts, train_labels)

    detector = HybridScamDetector(classifier=clf)

    # Urgent OTP demand (rule + statistical model should both trigger)
    res_scam = detector.analyze(
        "Urgent: Your account will be blocked within 24 hours. Click here to verify KYC immediately."
    )
    assert res_scam["is_scam"] is True
    assert res_scam["risk_tier"] in ("HIGH", "CRITICAL")
    assert res_scam["risk_score"] >= 50
    assert "rules" in res_scam["detection_sources"]
    assert res_scam["latency_ms"] < 200

    # Normal conversation
    res_safe = detector.analyze("Let's meet for coffee tomorrow at 4 PM.")
    assert res_safe["is_scam"] is False
    assert res_safe["risk_tier"] == "SAFE"
    assert res_safe["risk_score"] < 40


def test_hybrid_detector_keeps_the_rule_score_when_no_model_is_configured() -> None:
    message = "A routine synthetic test message."
    result = HybridScamDetector().analyze(message)

    assert result["model_probability"] is None
    assert result["detection_sources"] == ["baseline_clean"]


def test_transformer_reports_not_run_without_licensed_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.train_scam_transformer.check_gpu_and_dependencies",
        lambda: {"cuda_available": True, "transformers_installed": True},
    )

    result = run_transformer_experiment(tmp_path)

    assert result["status"] == "not_run"
    assert "Licensed labeled scam data" in result["reason"]
    assert not (tmp_path / "scam_transformer").exists()
