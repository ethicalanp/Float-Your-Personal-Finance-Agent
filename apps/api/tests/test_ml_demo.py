import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lightgbm import LGBMClassifier

from app.core.config import Settings
from app.services.borrow_features import FEATURE_COLUMNS, FEATURE_VERSION
from app.services.synthetic_borrow_demo import (
    clear_model_cache,
    evaluate_synthetic_borrow_demo,
)


def _write_demo_artifact(directory: Path) -> None:
    directory.mkdir()
    model_path = directory / "model.txt"
    model = LGBMClassifier(
        n_estimators=5,
        min_child_samples=1,
        verbosity=-1,
        force_col_wise=True,
        deterministic=True,
    )
    model.fit(np.zeros((4, len(FEATURE_COLUMNS))), np.array([0, 0, 1, 1]))
    model.booster_.save_model(str(model_path))
    metadata: dict[str, Any] = {
        "artifact_format_version": 1,
        "artifact_kind": "synthetic_borrow_demo",
        "dataset_status": "synthetic_only",
        "model_version": "synthetic_borrow_demo_test",
        "feature_version": FEATURE_VERSION,
        "feature_columns": list(FEATURE_COLUMNS),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "calibration": {"slope": 1.0, "intercept": 0.0},
        "validation_metrics": {"threshold": 0.5},
    }
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def _features() -> dict[str, Any]:
    return {
        "feature_version": FEATURE_VERSION,
        **{column: 0.1 for column in FEATURE_COLUMNS},
    }


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "ml_demo@example.com",
            "password": "StrongPassword123!",
            "full_name": "ML Demo User",
            "terms_accepted": True,
            "ai_data_processing_consent": True,
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_synthetic_borrow_model_checks_metadata_and_infers(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "model"
    _write_demo_artifact(artifact_dir)
    clear_model_cache()
    try:
        result = evaluate_synthetic_borrow_demo(_features(), artifact_dir)
    finally:
        clear_model_cache()

    assert result["model_track"] == "synthetic_borrow_demo"
    assert result["feature_version"] == FEATURE_VERSION
    assert result["synthetic_default_probability"] == pytest.approx(0.5)
    assert "not a real default-risk estimate" in result["warning"]


def test_synthetic_borrow_model_rejects_checksum_mismatch(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "model"
    _write_demo_artifact(artifact_dir)
    (artifact_dir / "model.txt").write_bytes(b"modified")
    clear_model_cache()
    try:
        with pytest.raises(RuntimeError, match="checksum"):
            evaluate_synthetic_borrow_demo(_features(), artifact_dir)
    finally:
        clear_model_cache()


def test_ml_demo_api_returns_503_when_demo_is_disabled(client: TestClient) -> None:
    headers = _auth_headers(client)
    response = client.post(
        "/api/v1/ml-demo/borrow",
        headers=headers,
        json=_features(),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_swagger_declares_separate_demo_endpoints(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/ml-demo/borrow" in paths
    assert "/api/v1/ml-demo/scam" in paths


def test_ml_demo_api_returns_503_when_enabled_without_model(
    client: TestClient,
    app: FastAPI,
) -> None:
    app.state.settings.enable_synthetic_ml_demos = True
    headers = _auth_headers(client)
    response = client.post(
        "/api/v1/ml-demo/borrow",
        headers=headers,
        json=_features(),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_ml_demo_api_serves_explicit_synthetic_model(
    tmp_path: Path,
    client: TestClient,
    app: FastAPI,
) -> None:
    artifact_dir = tmp_path / "model"
    _write_demo_artifact(artifact_dir)
    app.state.settings.enable_synthetic_ml_demos = True
    app.state.settings.synthetic_borrow_demo_model_path = str(artifact_dir)
    headers = _auth_headers(client)
    clear_model_cache()

    try:
        response = client.post(
            "/api/v1/ml-demo/borrow",
            headers=headers,
            json=_features(),
        )
    finally:
        clear_model_cache()

    assert response.status_code == 200
    assert response.json()["model_track"] == "synthetic_borrow_demo"
    assert response.json()["demo_flag"] is True


def test_synthetic_ml_demos_cannot_be_enabled_in_production() -> None:
    with pytest.raises(ValueError, match="must remain disabled in production"):
        Settings(
            app_env="production",
            enable_synthetic_ml_demos=True,
            jwt_secret_key="test-production-secret-key-with-at-least-32-characters",
            database_url="postgresql+psycopg://test:test@localhost/test",
            _env_file=None,
        )
