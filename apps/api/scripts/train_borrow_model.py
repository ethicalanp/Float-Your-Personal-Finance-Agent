#!/usr/bin/env python
"""Train a versioned cash-flow LightGBM artifact from a point-in-time labeled CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.services.borrow_features import FEATURE_COLUMNS, FEATURE_VERSION

TARGET_COLUMN = "target_default"
USER_COLUMN = "user_id"
AS_OF_COLUMN = "as_of_date"
MIN_CLASS_ROWS_PER_PARTITION = 10


def _read_training_rows(csv_path: Path) -> list[dict[str, Any]]:
    required_columns = {USER_COLUMN, AS_OF_COLUMN, TARGET_COLUMN, *FEATURE_COLUMNS}
    rows: list[dict[str, Any]] = []
    seen_users: set[str] = set()

    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError("Training CSV must have a header row.")
        missing_columns = required_columns.difference(reader.fieldnames)
        if missing_columns:
            raise ValueError(f"Training CSV is missing columns: {', '.join(sorted(missing_columns))}")

        for line_number, raw in enumerate(reader, start=2):
            user_id = (raw.get(USER_COLUMN) or "").strip()
            if not user_id:
                raise ValueError(f"CSV line {line_number}: {USER_COLUMN} must not be empty.")
            if user_id in seen_users:
                raise ValueError(
                    f"CSV has multiple snapshots for user {user_id!r}; "
                    "provide one point-in-time row per user to prevent cross-split leakage."
                )
            seen_users.add(user_id)

            try:
                as_of_date = date.fromisoformat((raw.get(AS_OF_COLUMN) or "").strip())
            except ValueError as exc:
                raise ValueError(f"CSV line {line_number}: {AS_OF_COLUMN} must be YYYY-MM-DD.") from exc

            try:
                target = int(raw[TARGET_COLUMN])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"CSV line {line_number}: {TARGET_COLUMN} must be 0 or 1.") from exc
            if target not in (0, 1):
                raise ValueError(f"CSV line {line_number}: {TARGET_COLUMN} must be 0 or 1.")

            feature_values: list[float] = []
            for column in FEATURE_COLUMNS:
                raw_value = (raw.get(column) or "").strip()
                if not raw_value:
                    feature_values.append(math.nan)
                    continue
                try:
                    value = float(raw_value)
                except ValueError as exc:
                    raise ValueError(
                        f"CSV line {line_number}: feature {column!r} must be numeric or blank."
                    ) from exc
                if not math.isfinite(value):
                    raise ValueError(
                        f"CSV line {line_number}: feature {column!r} must be finite or blank."
                    )
                feature_values.append(value)

            rows.append(
                {
                    USER_COLUMN: user_id,
                    AS_OF_COLUMN: as_of_date,
                    TARGET_COLUMN: target,
                    "features": feature_values,
                }
            )

    if not rows:
        raise ValueError("Training CSV has no data rows.")
    if len({row[AS_OF_COLUMN] for row in rows}) < 3:
        raise ValueError("Training CSV needs observations spanning at least three dates for temporal splits.")
    return sorted(rows, key=lambda row: row[AS_OF_COLUMN])


def _check_partition(name: str, rows: list[dict[str, Any]]) -> None:
    counts = Counter(row[TARGET_COLUMN] for row in rows)
    if any(counts[label] < MIN_CLASS_ROWS_PER_PARTITION for label in (0, 1)):
        raise ValueError(
            f"{name} split needs at least {MIN_CLASS_ROWS_PER_PARTITION} examples of each label; "
            f"got non-default={counts[0]}, default={counts[1]}."
        )


def _arrays(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([row["features"] for row in rows], dtype=float),
        np.asarray([row[TARGET_COLUMN] for row in rows], dtype=np.int32),
    )


def _metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        log_loss,
        roc_auc_score,
    )

    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "default_rate": float(np.mean(labels)),
    }


def _temporal_embargo_split(
    rows: list[dict[str, Any]],
    label_horizon_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Group rows strictly by as_of_date and apply an embargo gap of label_horizon_days between splits.

    This prevents future-label information leakage across all partitions:
    fit -> [embargo] -> early_stopping -> [embargo] -> calibration -> [embargo] -> test.
    """
    unique_dates = sorted({row[AS_OF_COLUMN] for row in rows})
    if len(unique_dates) < 4:
        raise ValueError("Training dataset requires observations spanning at least 4 distinct dates.")

    embargo = timedelta(days=label_horizon_days)
    total_span = (unique_dates[-1] - unique_dates[0]).days

    if total_span <= 3 * label_horizon_days:
        raise ValueError(
            f"Dataset date span ({total_span} days) is too short for a {label_horizon_days}-day "
            "label horizon across fit, early-stopping, calibration, and test partitions with required embargo gaps."
        )

    # 3 embargo gaps of label_horizon_days leave usable timeline days:
    usable_span = total_span - (3 * label_horizon_days)
    fit_days = max(1, int(usable_span * 0.50))
    early_days = max(1, int(usable_span * 0.16))
    calib_days = max(1, int(usable_span * 0.16))

    # 1. Fit partition
    min_date = unique_dates[0]
    fit_end_cutoff = min_date + timedelta(days=fit_days)
    fit_candidates = [d for d in unique_dates if d <= fit_end_cutoff]
    fit_end_date = fit_candidates[-1] if fit_candidates else min_date

    # 2. Early-stopping partition (after fit embargo)
    early_start_cutoff = fit_end_date + embargo
    early_candidates = [d for d in unique_dates if d > early_start_cutoff]
    if not early_candidates:
        raise ValueError("Insufficient date span: early-stopping partition has no observations after fit embargo.")

    early_end_cutoff = early_candidates[0] + timedelta(days=early_days)
    early_end_candidates = [d for d in early_candidates if d <= early_end_cutoff]
    early_stop_end_date = early_end_candidates[-1] if early_end_candidates else early_candidates[0]

    # 3. Calibration partition (after early-stopping embargo)
    calib_start_cutoff = early_stop_end_date + embargo
    calib_candidates = [d for d in unique_dates if d > calib_start_cutoff]
    if not calib_candidates:
        raise ValueError(
            "Insufficient date span: calibration partition has no observations "
            "after early-stopping embargo."
        )

    calib_end_cutoff = calib_candidates[0] + timedelta(days=calib_days)
    calib_end_candidates = [d for d in calib_candidates if d <= calib_end_cutoff]
    calib_end_date = calib_end_candidates[-1] if calib_end_candidates else calib_candidates[0]

    # 4. Test partition (after calibration embargo)
    test_start_cutoff = calib_end_date + embargo
    test_candidates = [d for d in unique_dates if d > test_start_cutoff]
    if not test_candidates:
        raise ValueError("Insufficient date span: test partition has no observations after calibration embargo.")

    fit_rows = [r for r in rows if r[AS_OF_COLUMN] <= fit_end_date]
    early_stop_rows = [r for r in rows if early_start_cutoff < r[AS_OF_COLUMN] <= early_stop_end_date]
    calibration_rows = [r for r in rows if calib_start_cutoff < r[AS_OF_COLUMN] <= calib_end_date]
    test_rows = [r for r in rows if r[AS_OF_COLUMN] > test_start_cutoff]

    return fit_rows, early_stop_rows, calibration_rows, test_rows


def train_model(
    csv_path: Path,
    output_dir: Path,
    *,
    data_source: str,
    label_horizon_days: int,
    model_version: str,
    num_boost_round: int = 1000,
) -> dict[str, Any]:
    if label_horizon_days <= 0:
        raise ValueError("label_horizon_days must be greater than zero.")
    if not data_source.strip():
        raise ValueError("data_source is required for model provenance.")
    if num_boost_round < 1:
        raise ValueError("num_boost_round must be at least one.")

    rows = _read_training_rows(csv_path)
    fit_rows, early_stop_rows, calibration_rows, test_rows = _temporal_embargo_split(
        rows, label_horizon_days=label_horizon_days
    )

    for split_name, split_rows in (
        ("training", fit_rows),
        ("early-stopping", early_stop_rows),
        ("calibration", calibration_rows),
        ("test", test_rows),
    ):
        _check_partition(split_name, split_rows)

    try:
        import lightgbm as lgb
        from sklearn.linear_model import LogisticRegression
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "Training requires the LightGBM native runtime and scikit-learn dependencies."
        ) from exc

    x_fit, y_fit = _arrays(fit_rows)
    x_early, y_early = _arrays(early_stop_rows)
    x_calibration, y_calibration = _arrays(calibration_rows)
    x_test, y_test = _arrays(test_rows)

    positives = int(np.sum(y_fit))
    negatives = len(y_fit) - positives
    training = lgb.Dataset(
        x_fit,
        label=y_fit,
        feature_name=list(FEATURE_COLUMNS),
        free_raw_data=False,
    )
    early_stopping = lgb.Dataset(
        x_early,
        label=y_early,
        feature_name=list(FEATURE_COLUMNS),
        reference=training,
        free_raw_data=False,
    )
    booster = lgb.train(
        params={
            "objective": "binary",
            "metric": ["binary_logloss", "auc"],
            "learning_rate": 0.03,
            "num_leaves": 15,
            "max_depth": 5,
            "min_data_in_leaf": 30,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.9,
            "bagging_freq": 1,
            "lambda_l1": 0.1,
            "lambda_l2": 1.0,
            "scale_pos_weight": negatives / positives,
            "seed": 2026,
            "feature_fraction_seed": 2026,
            "bagging_seed": 2026,
            "deterministic": True,
            "force_col_wise": True,
            "verbosity": -1,
        },
        train_set=training,
        num_boost_round=num_boost_round,
        valid_sets=[early_stopping],
        valid_names=["early_stopping"],
        callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)],
    )

    calibration_scores = booster.predict(x_calibration, raw_score=True)
    calibrator = LogisticRegression(C=1e6, max_iter=1000, solver="lbfgs")
    calibrator.fit(np.asarray(calibration_scores).reshape(-1, 1), y_calibration)
    calibration_slope = float(calibrator.coef_[0][0])
    calibration_intercept = float(calibrator.intercept_[0])
    if calibration_slope <= 0:
        raise ValueError(
            "Calibration learned a non-positive risk slope. Review the features, labels, and data time windows."
        )

    test_scores = np.asarray(booster.predict(x_test, raw_score=True), dtype=float)
    test_logits = np.clip(calibration_slope * test_scores + calibration_intercept, -709, 709)
    test_probabilities = 1.0 / (1.0 + np.exp(-test_logits))

    output_dir = output_dir.expanduser().resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing model artifact directory: {output_dir}")

    with tempfile.TemporaryDirectory(prefix=".borrow-model-", dir=output_dir.parent) as temp_dir:
        staging_dir = Path(temp_dir)
        model_path = staging_dir / "model.txt"
        booster.save_model(str(model_path), num_iteration=booster.best_iteration)
        model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()

        metadata: dict[str, Any] = {
            "model_format_version": 1,
            "model_version": f"lightgbm_cashflow_{model_version}",
            "feature_version": FEATURE_VERSION,
            "feature_columns": list(FEATURE_COLUMNS),
            "target_column": TARGET_COLUMN,
            "target_horizon_days": label_horizon_days,
            "training_data_source": data_source.strip(),
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "training_rows": len(rows),
            "splits": {
                "training_rows": len(fit_rows),
                "early_stopping_rows": len(early_stop_rows),
                "calibration_rows": len(calibration_rows),
                "test_rows": len(test_rows),
                "embargo_days": label_horizon_days,
                "training_period": [fit_rows[0][AS_OF_COLUMN].isoformat(), fit_rows[-1][AS_OF_COLUMN].isoformat()],
                "calibration_period": [
                    calibration_rows[0][AS_OF_COLUMN].isoformat(),
                    calibration_rows[-1][AS_OF_COLUMN].isoformat(),
                ],
                "test_period": [test_rows[0][AS_OF_COLUMN].isoformat(), test_rows[-1][AS_OF_COLUMN].isoformat()],
            },
            "best_iteration": int(booster.best_iteration),
            "calibration": {
                "method": "platt_scaling",
                "slope": calibration_slope,
                "intercept": calibration_intercept,
                "calibration_period": [
                    calibration_rows[0][AS_OF_COLUMN].isoformat(),
                    calibration_rows[-1][AS_OF_COLUMN].isoformat(),
                ],
            },
            "test_metrics": _metrics(y_test, test_probabilities),
            "model_sha256": model_hash,
        }
        (staging_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staging_dir.rename(output_dir)

    return metadata


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="Labeled point-in-time feature CSV.")
    parser.add_argument("--output", required=True, type=Path, help="New artifact directory; must not already exist.")
    parser.add_argument("--data-source", required=True, help="Dataset provenance, without personal data.")
    parser.add_argument(
        "--label-horizon-days",
        required=True,
        type=int,
        help="Fixed future outcome window represented by target_default.",
    )
    parser.add_argument("--model-version", default="v1.0.0")
    parser.add_argument("--num-boost-rounds", default=1000, type=int)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    metadata = train_model(
        args.csv,
        args.output,
        data_source=args.data_source,
        label_horizon_days=args.label_horizon_days,
        model_version=args.model_version,
        num_boost_round=args.num_boost_rounds,
    )
    print(
        json.dumps(
            {
                "artifact": str(args.output.resolve()),
                "test_metrics": metadata["test_metrics"],
                "model_version": metadata["model_version"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
