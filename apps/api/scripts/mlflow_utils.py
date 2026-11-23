"""Optional MLflow tracking for model artifacts and aggregate metrics."""

from __future__ import annotations

import math
import os
from typing import Any


def log_sklearn_experiment(
    *,
    model: Any,
    experiment_name: str,
    run_name: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    tags: dict[str, str],
    registered_model_name: str | None = None,
) -> dict[str, str | None]:
    """Log aggregate experiment data and a model artifact when tracking is configured."""
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        return {"status": "not_configured", "run_id": None, "model_version": None}

    try:
        import mlflow
        import mlflow.sklearn
    except ImportError as exc:
        raise RuntimeError(
            "MLflow tracking was requested through MLFLOW_TRACKING_URI, "
            "but the optional 'training' dependencies are not installed."
        ) from exc

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params({key: str(value) for key, value in params.items()})
        mlflow.log_metrics(
            {key: float(value) for key, value in metrics.items() if math.isfinite(float(value))}
        )
        mlflow.set_tags(tags)
        model_info = mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name=registered_model_name,
        )
        return {
            "status": "registered" if registered_model_name else "logged",
            "run_id": run.info.run_id,
            "model_version": getattr(model_info, "registered_model_version", None),
        }
