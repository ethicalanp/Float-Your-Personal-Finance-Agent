#!/usr/bin/env python
"""Train an isolated, synthetic-only Borrow feature demo model."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn  # noqa: F401
from lightgbm import LGBMClassifier
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit

from app.services.borrow_features import FEATURE_COLUMNS, FEATURE_VERSION
from scripts.mlflow_utils import log_sklearn_experiment
from scripts.model_evaluation import (
    apply_platt_calibration,
    binary_metrics,
    fit_platt_calibration,
    select_f1_threshold,
)

DEFAULT_DATA_DIR = Path("artifacts") / "synthetic_ml_v2"
DEFAULT_OUTPUT_DIR = DEFAULT_DATA_DIR / "borrow_model_lightgbm"
MODEL_FILENAME = "model.txt"
METADATA_FILENAME = "metadata.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_dataset(data_dir: Path) -> tuple[pd.DataFrame, pd.Series, dict[str, Any]]:
    data_path = data_dir / "borrow_features_synthetic.csv"
    manifest_path = data_dir / "synthetic_dataset_manifest.json"
    if not data_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"Synthetic Borrow CSV and manifest are required in {data_dir}.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_status") != "synthetic_pipeline_test_only":
        raise ValueError("This demo trainer only accepts a manifest-marked synthetic dataset.")
    if manifest.get("borrow_feature_version") != FEATURE_VERSION:
        raise ValueError("Synthetic dataset feature version does not match the API contract.")
    data = pd.read_csv(data_path)
    required = {"as_of_date", "synthetic_target_default", *FEATURE_COLUMNS}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Synthetic Borrow CSV is missing columns: {', '.join(sorted(missing))}")
    data["as_of_date"] = pd.to_datetime(data["as_of_date"], errors="raise").dt.date
    labels = data.pop("synthetic_target_default").astype(int)
    data = data.sort_values("as_of_date")
    labels = labels.loc[data.index].reset_index(drop=True)
    data = data.reset_index(drop=True)
    features = data.loc[:, FEATURE_COLUMNS].apply(pd.to_numeric, errors="raise")
    if not set(labels.unique()).issubset({0, 1}) or labels.nunique() != 2:
        raise ValueError("Synthetic target must contain both binary classes.")
    if features.isin([np.inf, -np.inf]).any().any():
        raise ValueError("Synthetic features must be finite or missing.")
    return data, labels, manifest


def train_synthetic_borrow_demo(
    data_dir: Path,
    output_dir: Path,
    *,
    model_version: str = "v1.0.0",
    tune_iterations: int = 4,
    seed: int = 2026,
    registered_model_name: str | None = None,
) -> dict[str, Any]:
    if tune_iterations < 1:
        raise ValueError("tune_iterations must be at least one.")
    data_dir = data_dir.expanduser().resolve()
    data, labels, manifest = _read_dataset(data_dir)
    dates = data["as_of_date"].tolist()
    x = data.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
    y = labels.to_numpy(dtype=np.int32)

    train_end = int(len(data) * 0.60)
    calibration_end = int(len(data) * 0.75)
    validation_end = int(len(data) * 0.85)
    partitions = {
        "training": slice(0, train_end),
        "calibration": slice(train_end, calibration_end),
        "validation": slice(calibration_end, validation_end),
        "test": slice(validation_end, len(data)),
    }
    if min(np.bincount(y[part], minlength=2).min() for part in partitions.values()) < 3:
        raise ValueError("Every chronological partition must contain at least three examples per class.")

    base_model = LGBMClassifier(
        objective="binary",
        class_weight="balanced",
        random_state=seed,
        n_jobs=1,
        verbosity=-1,
        deterministic=True,
        force_col_wise=True,
        min_child_samples=10,
    )
    parameter_space = {
        "n_estimators": [40, 80, 120, 180],
        "learning_rate": [0.03, 0.06, 0.1],
        "num_leaves": [7, 15, 23],
        "max_depth": [3, 5, -1],
        "reg_lambda": [0.0, 0.5, 1.0],
    }
    search = RandomizedSearchCV(
        base_model,
        parameter_space,
        n_iter=tune_iterations,
        scoring="roc_auc",
        cv=TimeSeriesSplit(n_splits=3),
        random_state=seed,
        n_jobs=1,
        refit=True,
    )
    search.fit(x[partitions["training"]], y[partitions["training"]])
    model = search.best_estimator_

    calibration = partitions["calibration"]
    calibration_raw = model.predict_proba(x[calibration])[:, 1]
    slope, intercept = fit_platt_calibration(calibration_raw, y[calibration])
    validation = partitions["validation"]
    validation_probabilities = apply_platt_calibration(
        model.predict_proba(x[validation])[:, 1],
        slope,
        intercept,
    )
    threshold, validation_metrics = select_f1_threshold(y[validation], validation_probabilities)
    test = partitions["test"]
    test_probabilities = apply_platt_calibration(
        model.predict_proba(x[test])[:, 1],
        slope,
        intercept,
    )
    test_metrics = binary_metrics(y[test], test_probabilities, threshold)

    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing model artifact directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".borrow-demo-", dir=output_dir.parent) as temp:
        staging = Path(temp)
        model_path = staging / MODEL_FILENAME
        model.booster_.save_model(str(model_path))
        metadata: dict[str, Any] = {
            "artifact_format_version": 1,
            "artifact_kind": "synthetic_borrow_demo",
            "dataset_status": "synthetic_only",
            "model_version": f"synthetic_borrow_demo_{model_version}",
            "feature_version": FEATURE_VERSION,
            "feature_columns": list(FEATURE_COLUMNS),
            "target_column": "synthetic_target_default",
            "target_semantics": "Toy scenario label generated from synthetic features; not a real outcome.",
            "target_rule": manifest["borrow_target_rule"],
            "dataset_sha256": _sha256(data_dir / "borrow_features_synthetic.csv"),
            "dataset_rows": len(data),
            "split_method": "chronological 60/15/10/15; rows ordered by as_of_date",
            "split_rows": {name: part.stop - part.start for name, part in partitions.items()},
            "split_periods": {
                name: [dates[part.start].isoformat(), dates[part.stop - 1].isoformat()]
                for name, part in partitions.items()
            },
            "seed": seed,
            "tuning": {"method": "RandomizedSearchCV on training partition only", "best_params": search.best_params_},
            "calibration": {"method": "platt_scaling", "slope": slope, "intercept": intercept},
            "validation_metrics": {"threshold": threshold, **validation_metrics},
            "test_metrics": test_metrics,
            "model_sha256": _sha256(model_path),
            "limitations": [
                "Synthetic-only model for an isolated demo endpoint.",
                "Predictions are not estimates of real default risk and must not be used for real users.",
                "The production Borrow API loader does not accept this artifact kind.",
            ],
        }
        mlflow_result = log_sklearn_experiment(
            model=model,
            experiment_name="synthetic-borrow-demo",
            run_name=metadata["model_version"],
            params={**search.best_params_, "seed": seed},
            metrics={f"test_{key}": value for key, value in test_metrics.items() if isinstance(value, (int, float))},
            tags={"dataset_status": "synthetic_only", "model_track": "borrow_demo"},
            registered_model_name=registered_model_name,
        )
        metadata["mlflow"] = mlflow_result
        (staging / METADATA_FILENAME).write_text(
            json.dumps(metadata, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staging.rename(output_dir)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-version", default="v1.0.0")
    parser.add_argument("--tune-iterations", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--registered-model-name")
    args = parser.parse_args()
    result = train_synthetic_borrow_demo(
        args.data_dir,
        args.output_dir,
        model_version=args.model_version,
        tune_iterations=args.tune_iterations,
        seed=args.seed,
        registered_model_name=args.registered_model_name,
    )
    print(
        json.dumps(
            {
                "artifact": str(args.output_dir.resolve()),
                "test_metrics": result["test_metrics"],
                "mlflow": result["mlflow"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
