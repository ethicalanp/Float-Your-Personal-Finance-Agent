import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.synthetic_scam_demo import clear_model_cache, evaluate_synthetic_scam_demo
from scripts.generate_synthetic_ml_data import generate_synthetic_datasets
from scripts.train_synthetic_scam_demo import train_synthetic_scam_demo


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "synthetic_scam_demo@example.com",
            "password": "StrongPassword123!",
            "full_name": "Synthetic Scam Demo User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_scam_demo_uses_grouped_splits_and_serves_explicit_artifact(
    tmp_path: Path,
    app: FastAPI,
    client: TestClient,
) -> None:
    data_dir = tmp_path / "synthetic_data"
    output_dir = tmp_path / "scam_model"
    generate_synthetic_datasets(data_dir, row_count=200)
    comparison = train_synthetic_scam_demo(data_dir, output_dir)

    split_groups = {
        name: set(groups)
        for name, groups in comparison["split_groups"].items()
    }
    split_names = list(split_groups)
    for index, name in enumerate(split_names):
        assert all(
            not split_groups[name].intersection(split_groups[other])
            for other in split_names[index + 1 :]
        )
    assert set(comparison["per_language"]) == {"en", "ml", "manglish"}
    assert "pr_auc" in comparison["per_language"]["en"]["tfidf"]
    assert "expected_calibration_error_10_bins" in comparison["per_language"]["en"]["tfidf"]
    assert "SYNTHETIC TEST ONLY" not in json.dumps(comparison)
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["dataset_status"] == "synthetic_only"
    assert metadata["mlflow"]["status"] == "not_configured"

    clear_model_cache()
    try:
        prediction = evaluate_synthetic_scam_demo(
            "SYNTHETIC TEST ONLY: a pretend bank asks for an OTP.",
            output_dir,
        )
        app.state.settings.enable_synthetic_ml_demos = True
        app.state.settings.synthetic_scam_demo_model_path = str(output_dir)
        response = client.post(
            "/api/v1/ml-demo/scam",
            headers=_auth_headers(client),
            json={"message": "A demo message with an OTP request."},
        )
    finally:
        clear_model_cache()

    assert prediction["model_track"] == "synthetic_scam_demo"
    assert 0.0 <= prediction["synthetic_scam_probability"] <= 1.0
    assert "not validated for real scam detection" in prediction["warning"]
    assert response.status_code == 200
    assert response.json()["model_track"] == "synthetic_scam_demo"


def test_scam_demo_api_returns_503_when_enabled_without_model(
    app: FastAPI,
    client: TestClient,
) -> None:
    app.state.settings.enable_synthetic_ml_demos = True
    app.state.settings.synthetic_scam_demo_model_path = None
    response = client.post(
        "/api/v1/ml-demo/scam",
        headers=_auth_headers(client),
        json={"message": "A synthetic demo message."},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_scam_demo_loader_rejects_checksum_mismatch(tmp_path: Path) -> None:
    data_dir = tmp_path / "synthetic_data"
    output_dir = tmp_path / "scam_model"
    generate_synthetic_datasets(data_dir, row_count=200)
    train_synthetic_scam_demo(data_dir, output_dir)
    model_path = output_dir / "model.joblib"
    model_path.write_bytes(model_path.read_bytes() + b"tampered")
    clear_model_cache()

    try:
        with pytest.raises(RuntimeError, match="checksum"):
            evaluate_synthetic_scam_demo("demo inference", output_dir)
    finally:
        clear_model_cache()
