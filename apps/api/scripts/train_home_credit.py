#!/usr/bin/env python
"""Production training pipeline for Home Credit Default Risk using LightGBM.

Features:
- Replaces sentinel employment days (365243) with NaN
- Computes core domain financial ratios (Credit/Income, Annuity/Income, Annuity/Credit, etc.)
- Handles class imbalance via scale_pos_weight
- Calibrates decision threshold on validation set to maximize F1 (preventing test set leakage)
- Tracks experiments and logs parameters/metrics/artifacts to MLflow (with graceful local fallback)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn  # noqa: F401
from lightgbm import LGBMClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
)
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from scripts.mlflow_utils import log_sklearn_experiment
from scripts.model_evaluation import (
    apply_platt_calibration,
    binary_metrics,
    fit_platt_calibration,
    select_f1_threshold,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SENTINEL_DAYS_EMPLOYED = 365243
ENGINEERED_FEATURES = [
    "CREDIT_INCOME_RATIO",
    "ANNUITY_INCOME_RATIO",
    "ANNUITY_CREDIT_RATIO",
    "GOODS_CREDIT_RATIO",
    "INCOME_PER_PERSON",
    "EMPLOYED_TO_AGE_RATIO",
]


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Perform division replacing zero denominators and infinite values with NaN."""
    denom_clean = denominator.replace(0, np.nan)
    result = numerator / denom_clean
    return result.replace([np.inf, -np.inf], np.nan)


def engineer_financial_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create domain-specific financial ratios and clean sentinel values."""
    data = df.copy()

    # Sentinel value handling: 365243 is a known anomaly for unemployed/retired in Home Credit
    if "DAYS_EMPLOYED" in data.columns:
        data["DAYS_EMPLOYED"] = data["DAYS_EMPLOYED"].replace(SENTINEL_DAYS_EMPLOYED, np.nan)

    if "AMT_CREDIT" in data.columns and "AMT_INCOME_TOTAL" in data.columns:
        data["CREDIT_INCOME_RATIO"] = safe_divide(data["AMT_CREDIT"], data["AMT_INCOME_TOTAL"])

    if "AMT_ANNUITY" in data.columns and "AMT_INCOME_TOTAL" in data.columns:
        data["ANNUITY_INCOME_RATIO"] = safe_divide(data["AMT_ANNUITY"], data["AMT_INCOME_TOTAL"])

    if "AMT_ANNUITY" in data.columns and "AMT_CREDIT" in data.columns:
        data["ANNUITY_CREDIT_RATIO"] = safe_divide(data["AMT_ANNUITY"], data["AMT_CREDIT"])

    if "AMT_GOODS_PRICE" in data.columns and "AMT_CREDIT" in data.columns:
        data["GOODS_CREDIT_RATIO"] = safe_divide(data["AMT_GOODS_PRICE"], data["AMT_CREDIT"])

    if "AMT_INCOME_TOTAL" in data.columns and "CNT_FAM_MEMBERS" in data.columns:
        data["INCOME_PER_PERSON"] = safe_divide(data["AMT_INCOME_TOTAL"], data["CNT_FAM_MEMBERS"])

    if "DAYS_EMPLOYED" in data.columns and "DAYS_BIRTH" in data.columns:
        data["EMPLOYED_TO_AGE_RATIO"] = safe_divide(
            data["DAYS_EMPLOYED"].abs(), data["DAYS_BIRTH"].abs()
        )

    return data


def build_pipeline(
    numeric_features: list[str],
    categorical_features: list[str],
    scale_pos_weight: float = 1.0,
    n_estimators: int = 500,
    learning_rate: float = 0.03,
    num_leaves: int = 31,
    max_depth: int = 7,
    colsample_bytree: float = 0.8,
    subsample: float = 0.8,
) -> Pipeline:
    """Build sklearn Pipeline combining preprocessing and LightGBM classifier."""
    numeric_transformer = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    categorical_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ]
    )

    model = LGBMClassifier(
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        num_leaves=num_leaves,
        max_depth=max_depth,
        colsample_bytree=colsample_bytree,
        subsample=subsample,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )

    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def find_optimal_threshold(y_val: np.ndarray, y_val_proba: np.ndarray) -> tuple[float, float, float, float]:
    """Identify probability threshold maximizing F1 on the validation set."""
    precision, recall, thresholds = precision_recall_curve(y_val, y_val_proba)
    # Exclude division by zero
    f1_scores = 2 * (precision[:-1] * recall[:-1]) / (precision[:-1] + recall[:-1] + 1e-10)
    best_idx = int(np.argmax(f1_scores))
    best_threshold = float(thresholds[best_idx])
    return (
        best_threshold,
        float(precision[best_idx]),
        float(recall[best_idx]),
        float(f1_scores[best_idx]),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train_home_credit(
    data_path: Path,
    output_dir: Path,
    *,
    data_source: str,
    terms_reference: str,
    sample_size: int | None = None,
    tune_hyperparameters: bool = False,
    n_iter: int = 5,
    registered_model_name: str | None = None,
) -> dict[str, Any]:
    """Run a provenance-gated, research-only Home Credit benchmark."""
    if not data_source.strip() or not terms_reference.strip():
        raise ValueError("Verified data source and terms reference are required before training.")
    if tune_hyperparameters and n_iter < 1:
        raise ValueError("n_iter must be at least one when tuning is enabled.")

    logger.info("Loading Home Credit dataset from %s", data_path)
    df = pd.read_csv(data_path)
    logger.info("Loaded dataset shape: %s", df.shape)
    source_rows = len(df)

    if sample_size and sample_size < len(df):
        logger.info("Subsampling to %d rows for quick training/testing", sample_size)
        df = df.sample(n=sample_size, random_state=42).reset_index(drop=True)

    target_col = "TARGET"
    id_col = "SK_ID_CURR"
    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found in dataset.")

    # Feature engineering
    logger.info("Applying domain financial feature engineering...")
    df_fe = engineer_financial_features(df)

    cols_to_drop = [target_col]
    if id_col in df_fe.columns:
        cols_to_drop.append(id_col)

    x_data = df_fe.drop(columns=cols_to_drop)
    y_data = df_fe[target_col].to_numpy(dtype=np.int32)

    # Separate partitions keep tuning, calibration, threshold selection, and test evaluation isolated.
    x_train, x_remaining, y_train, y_remaining = train_test_split(
        x_data, y_data, test_size=0.40, random_state=42, stratify=y_data
    )
    x_calibration, x_val_test, y_calibration, y_val_test = train_test_split(
        x_remaining, y_remaining, test_size=0.75, random_state=42, stratify=y_remaining
    )
    x_val, x_test, y_val, y_test = train_test_split(
        x_val_test, y_val_test, test_size=0.50, random_state=42, stratify=y_val_test
    )

    numeric_features = x_train.select_dtypes(include=["number"]).columns.tolist()
    categorical_features = x_train.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    neg_count = int(np.sum(y_train == 0))
    pos_count = int(np.sum(y_train == 1))
    scale_pos_weight = float(neg_count / max(pos_count, 1))
    logger.info(
        "Class distribution in train: 0=%d, 1=%d. scale_pos_weight=%.3f",
        neg_count,
        pos_count,
        scale_pos_weight,
    )

    if tune_hyperparameters:
        logger.info("Running RandomizedSearchCV (n_iter=%d)...", n_iter)
        pipeline = build_pipeline(
            numeric_features=numeric_features,
            categorical_features=categorical_features,
            scale_pos_weight=scale_pos_weight,
        )
        param_dist = {
            "model__n_estimators": [300, 500, 800],
            "model__learning_rate": [0.02, 0.03, 0.05],
            "model__num_leaves": [20, 31, 50],
            "model__max_depth": [5, 7, 10],
            "model__colsample_bytree": [0.7, 0.8, 1.0],
            "model__subsample": [0.8, 1.0],
        }
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        search = RandomizedSearchCV(
            pipeline,
            param_distributions=param_dist,
            n_iter=n_iter,
            scoring="average_precision",
            cv=cv,
            random_state=42,
            n_jobs=-1,
            refit=True,
        )
        search.fit(x_train, y_train)
        best_pipeline = search.best_estimator_
        best_params = search.best_params_
        logger.info("Best CV PR-AUC: %.4f with params: %s", search.best_score_, best_params)
    else:
        logger.info("Training LightGBM pipeline with robust default financial hyperparameters...")
        best_pipeline = build_pipeline(
            numeric_features=numeric_features,
            categorical_features=categorical_features,
            scale_pos_weight=scale_pos_weight,
            n_estimators=400,
            learning_rate=0.03,
            num_leaves=31,
            max_depth=7,
        )
        best_pipeline.fit(x_train, y_train)
        best_params = {"n_estimators": 400, "learning_rate": 0.03, "scale_pos_weight": scale_pos_weight}

    logger.info("Fitting probability calibration on the separate calibration partition...")
    raw_calibration = best_pipeline.predict_proba(x_calibration)[:, 1]
    calibration_slope, calibration_intercept = fit_platt_calibration(raw_calibration, y_calibration)

    logger.info("Selecting the operating threshold on the validation partition...")
    val_proba = apply_platt_calibration(
        best_pipeline.predict_proba(x_val)[:, 1],
        calibration_slope,
        calibration_intercept,
    )
    best_thresh, validation_metrics = select_f1_threshold(y_val, val_proba)
    logger.info(
        "Validation Threshold=%.4f (Val Precision=%.4f, Recall=%.4f, F1=%.4f)",
        best_thresh,
        validation_metrics["precision"],
        validation_metrics["recall"],
        validation_metrics["f1"],
    )

    logger.info("Evaluating on the untouched held-out test partition...")
    test_proba = apply_platt_calibration(
        best_pipeline.predict_proba(x_test)[:, 1],
        calibration_slope,
        calibration_intercept,
    )
    test_metrics = binary_metrics(y_test, test_proba, best_thresh)
    test_pred = (test_proba >= best_thresh).astype(int)
    cm = confusion_matrix(y_test, test_pred).tolist()

    logger.info(
        "Test ROC-AUC: %.4f | PR-AUC: %.4f | F1: %.4f | Precision: %.4f | Recall: %.4f",
        test_metrics["roc_auc"],
        test_metrics["pr_auc"],
        test_metrics["f1"],
        test_metrics["precision"],
        test_metrics["recall"],
    )
    logger.info("Confusion Matrix: %s", cm)

    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing Home Credit research artifacts: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".home-credit-", dir=output_dir.parent) as temp:
        staging = Path(temp)
        model_path = staging / "home_credit_lightgbm_engineered.joblib"
        threshold_path = staging / "borrow_threshold.json"
        metadata_path = staging / "home_credit_metadata.json"
        joblib.dump(best_pipeline, model_path)
        threshold_path.write_text(
            json.dumps(
                {
                    "threshold": best_thresh,
                    "selection_method": "maximum_validation_f1",
                    **validation_metrics,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        test_metrics["confusion_matrix"] = cm
        metadata: dict[str, Any] = {
            "artifact_format_version": 1,
            "artifact_kind": "home_credit_research",
            "dataset_status": "research_only",
            "model_name": "HomeCredit_LightGBM_Engineered",
            "dataset_provenance": {
                "data_source": data_source.strip(),
                "terms_reference": terms_reference.strip(),
            },
            "dataset_sha256": _sha256(data_path),
            "dataset_rows": len(df),
            "source_rows": source_rows,
            "sample_size": sample_size,
            "sampling_seed": 42,
            "split_method": "stratified random 60/10/15/15; train/calibration/validation/test",
            "split_seed": 42,
            "split_rows": {
                "training": len(x_train),
                "calibration": len(x_calibration),
                "validation": len(x_val),
                "test": len(x_test),
            },
            "test_row_indices": x_test.index.tolist(),
            "target_definition": {
                "column": "TARGET",
                "semantics": "Home Credit Default Risk benchmark target; not a Borrow cash-flow outcome.",
            },
            "feature_columns": x_data.columns.tolist(),
            "numeric_features": numeric_features,
            "categorical_features": categorical_features,
            "scale_pos_weight": scale_pos_weight,
            "best_hyperparameters": best_params,
            "engineered_features": ENGINEERED_FEATURES,
            "calibration": {
                "method": "platt_scaling",
                "slope": calibration_slope,
                "intercept": calibration_intercept,
            },
            "validation_metrics": {"threshold": best_thresh, **validation_metrics},
            "test_metrics": test_metrics,
            "model_sha256": _sha256(model_path),
            "limitations": [
                "Research-only Home Credit target; not the production cash-flow Borrow outcome.",
                "Dataset terms must be independently verified and recorded before training or sharing results.",
                "No fairness approval or production suitability is implied by these benchmark metrics.",
            ],
        }
        base_rate = float(np.mean(y_train))
        mlflow_result = log_sklearn_experiment(
            model=best_pipeline,
            experiment_name="HomeCredit-Research",
            run_name="home_credit_lightgbm_research",
            params={**best_params, "scale_pos_weight": scale_pos_weight},
            metrics={
                f"test_{key}": float(value)
                for key, value in test_metrics.items()
                if isinstance(value, (int, float))
            },
            tags={"dataset_status": "research_only", "model_track": "home_credit"},
            registered_model_name=registered_model_name,
        )
        metadata["mlflow"] = mlflow_result
        metadata["baseline_test_metrics"] = {
            "roc_auc": 0.5,
            "pr_auc": float(average_precision_score(y_test, np.full(len(y_test), base_rate))),
            "brier_score": float(np.mean((y_test - base_rate) ** 2)),
            "positive_rate": float(np.mean(y_test)),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staging.rename(output_dir)

    logger.info("Exported research-only artifacts to %s", output_dir)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Home Credit LightGBM Pipeline")
    parser.add_argument("--data-path", type=Path, default=Path("data/raw/application_train.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--data-source", required=True, help="Verified dataset source to record in metadata")
    parser.add_argument("--terms-reference", required=True, help="Verified dataset terms/license reference")
    parser.add_argument("--sample-size", type=int, default=None, help="Optional subsample count for rapid verification")
    parser.add_argument("--tune", action="store_true", help="Perform randomized search hyperparameter tuning")
    parser.add_argument("--n-iter", type=int, default=5, help="Number of tuning iterations")
    parser.add_argument("--registered-model-name", help="Optional MLflow registered model name")

    args = parser.parse_args()
    train_home_credit(
        data_path=args.data_path,
        output_dir=args.output_dir,
        data_source=args.data_source,
        terms_reference=args.terms_reference,
        sample_size=args.sample_size,
        tune_hyperparameters=args.tune,
        n_iter=args.n_iter,
        registered_model_name=args.registered_model_name,
    )


if __name__ == "__main__":
    main()
