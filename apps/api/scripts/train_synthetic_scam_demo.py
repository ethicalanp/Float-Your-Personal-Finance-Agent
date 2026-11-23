#!/usr/bin/env python
"""Train and evaluate an isolated TF-IDF scam demo on synthetic templates only."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

from app.services.scam_classifier import ScamClassifier
from app.services.scam_detector import analyze_scam_message
from scripts.mlflow_utils import log_sklearn_experiment
from scripts.model_evaluation import (
    apply_platt_calibration,
    binary_metrics,
    fit_platt_calibration,
    select_f1_threshold,
)

DEFAULT_DATA_DIR = Path("artifacts") / "synthetic_ml_v2"
DEFAULT_OUTPUT_DIR = DEFAULT_DATA_DIR / "scam_model"
MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"
COMPARISON_FILENAME = "comparison.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_data(data_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    data_path = data_dir / "scam_messages_synthetic.csv"
    manifest_path = data_dir / "synthetic_dataset_manifest.json"
    if not data_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"Synthetic scam CSV and manifest are required in {data_dir}.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_status") != "synthetic_pipeline_test_only":
        raise ValueError("This demo trainer only accepts a manifest-marked synthetic dataset.")
    if manifest.get("scam_split_group_column") != "template_group":
        raise ValueError("Synthetic scam manifest does not declare the expected template grouping.")

    data = pd.read_csv(data_path)
    required = {"text", "synthetic_is_scam", "lang", "template_group"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Synthetic scam CSV is missing columns: {', '.join(sorted(missing))}")
    if data[list(required)].isna().any().any():
        raise ValueError("Synthetic scam data must not have missing text, labels, languages, or groups.")
    data["synthetic_is_scam"] = data["synthetic_is_scam"].astype(int)
    if set(data["synthetic_is_scam"].unique()) != {0, 1}:
        raise ValueError("Synthetic scam labels must contain both binary classes.")

    group_values = data.groupby("template_group").agg(
        languages=("lang", "nunique"),
        labels=("synthetic_is_scam", "nunique"),
    )
    if (group_values["languages"] != 1).any() or (group_values["labels"] != 1).any():
        raise ValueError("Each template group must belong to exactly one language and label.")
    return data, manifest


def _group_partitions(data: pd.DataFrame, seed: int) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)
    group_metadata = data.groupby("template_group", sort=True).agg(
        lang=("lang", "first"),
        label=("synthetic_is_scam", "first"),
    )
    assignments: dict[str, str] = {}
    for (language, label), rows in group_metadata.groupby(["lang", "label"], sort=True):
        groups = rows.index.tolist()
        rng.shuffle(groups)
        if len(groups) < 4:
            raise ValueError(
                f"At least four independent template groups are required for {language!r}, label {label}."
            )
        assignments[groups[0]] = "calibration"
        assignments[groups[1]] = "validation"
        assignments[groups[2]] = "test"
        for group in groups[3:]:
            assignments[group] = "training"

    partitions = {
        name: data.loc[data["template_group"].map(assignments) == name].reset_index(drop=True)
        for name in ("training", "calibration", "validation", "test")
    }
    if any(part.empty for part in partitions.values()):
        raise ValueError("Every group-based synthetic scam partition must contain rows.")
    group_sets = {
        name: set(part["template_group"])
        for name, part in partitions.items()
    }
    names = list(group_sets)
    for index, name in enumerate(names):
        if any(group_sets[name] & group_sets[other] for other in names[index + 1 :]):
            raise RuntimeError("Template groups leaked across synthetic scam partitions.")
    for partition in partitions.values():
        if set(partition["lang"].unique()) != set(data["lang"].unique()):
            raise ValueError("Every scam split must contain examples from every language.")
        if set(partition["synthetic_is_scam"].unique()) != {0, 1}:
            raise ValueError("Every scam split must contain both labels.")
    return partitions


def _predict_calibrated(
    classifier: ScamClassifier,
    texts: list[str],
    slope: float,
    intercept: float,
) -> tuple[np.ndarray, float]:
    probabilities = []
    elapsed_ms = []
    for text in texts:
        start = time.perf_counter()
        raw_probability = float(classifier.pipeline.predict_proba([text])[0, 1])
        probability = float(apply_platt_calibration(np.asarray([raw_probability]), slope, intercept)[0])
        elapsed_ms.append((time.perf_counter() - start) * 1000)
        probabilities.append(probability)
    return np.asarray(probabilities), float(np.mean(elapsed_ms))


def _rule_baseline_metrics(data: pd.DataFrame) -> dict[str, Any]:
    predictions = []
    scores = []
    latency_ms = []
    for text in data["text"].astype(str):
        start = time.perf_counter()
        result = analyze_scam_message(text)
        latency_ms.append((time.perf_counter() - start) * 1000)
        score = float(result.get("risk_score", 0.0)) / 100.0
        scores.append(score)
        predictions.append(int(result.get("risk_tier") in ("HIGH", "CRITICAL")))
    labels = data["synthetic_is_scam"].to_numpy(dtype=np.int32)
    score_array = np.asarray(scores)
    prediction_array = np.asarray(predictions, dtype=np.int32)
    return {
        "precision": float(precision_score(labels, prediction_array, zero_division=0)),
        "recall": float(recall_score(labels, prediction_array, zero_division=0)),
        "f1": float(f1_score(labels, prediction_array, zero_division=0)),
        "pr_auc_from_rule_score": float(average_precision_score(labels, score_array)),
        "avg_latency_ms": float(np.mean(latency_ms)),
    }


def train_synthetic_scam_demo(
    data_dir: Path,
    output_dir: Path,
    *,
    seed: int = 2026,
    registered_model_name: str | None = None,
) -> dict[str, Any]:
    data_dir = data_dir.expanduser().resolve()
    data, manifest = _load_data(data_dir)
    partitions = _group_partitions(data, seed)

    classifier = ScamClassifier()
    training = partitions["training"]
    classifier.train(
        training["text"].astype(str).tolist(),
        training["synthetic_is_scam"].astype(int).tolist(),
    )
    calibration = partitions["calibration"]
    raw_calibration = np.asarray(
        classifier.pipeline.predict_proba(calibration["text"].astype(str).tolist())[:, 1]
    )
    slope, intercept = fit_platt_calibration(
        raw_calibration,
        calibration["synthetic_is_scam"].to_numpy(dtype=np.int32),
    )
    validation = partitions["validation"]
    validation_probabilities, _ = _predict_calibrated(
        classifier,
        validation["text"].astype(str).tolist(),
        slope,
        intercept,
    )
    threshold, validation_metrics = select_f1_threshold(
        validation["synthetic_is_scam"].to_numpy(dtype=np.int32),
        validation_probabilities,
    )

    test = partitions["test"]
    test_probabilities, model_latency = _predict_calibrated(
        classifier,
        test["text"].astype(str).tolist(),
        slope,
        intercept,
    )
    test_labels = test["synthetic_is_scam"].to_numpy(dtype=np.int32)
    model_metrics = binary_metrics(test_labels, test_probabilities, threshold)
    model_metrics["avg_latency_ms"] = model_latency
    rule_metrics = _rule_baseline_metrics(test)
    per_language: dict[str, Any] = {}
    for language in sorted(test["lang"].unique()):
        mask = test["lang"].to_numpy() == language
        lang_labels = test_labels[mask]
        lang_probabilities = test_probabilities[mask]
        lang_threshold_metrics = binary_metrics(lang_labels, lang_probabilities, threshold)
        lang_rule_data = test.loc[test["lang"] == language]
        per_language[language] = {
            "tfidf": lang_threshold_metrics,
            "rule_baseline": _rule_baseline_metrics(lang_rule_data),
        }

    comparison = {
        "dataset_status": "synthetic_only",
        "split_method": "disjoint template_group holdouts",
        "split_rows": {name: len(part) for name, part in partitions.items()},
        "split_groups": {
            name: sorted(part["template_group"].unique().tolist())
            for name, part in partitions.items()
        },
        "threshold": threshold,
        "validation_metrics": validation_metrics,
        "test_tfidf": model_metrics,
        "test_rule_baseline": rule_metrics,
        "per_language": per_language,
        "limitations": [
            "All messages and labels are generated from templates; this is not licensed real-world data.",
            "Metrics only verify the isolated training and inference pipeline.",
            "Do not interpret the results as real scam-detection quality or deploy this model.",
        ],
    }

    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing model artifact directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".scam-demo-", dir=output_dir.parent) as temp:
        staging = Path(temp)
        model_path = staging / MODEL_FILENAME
        classifier.save(model_path)
        mlflow_result = log_sklearn_experiment(
            model=classifier.pipeline,
            experiment_name="synthetic-scam-demo",
            run_name="synthetic_scam_demo_v1",
            params={"seed": seed, "threshold": threshold},
            metrics={
                f"test_{key}": value
                for key, value in model_metrics.items()
                if isinstance(value, (int, float))
            },
            tags={"dataset_status": "synthetic_only", "model_track": "scam_demo"},
            registered_model_name=registered_model_name,
        )
        metadata = {
            "artifact_format_version": 1,
            "artifact_kind": "synthetic_scam_demo",
            "dataset_status": "synthetic_only",
            "model_version": "synthetic_scam_demo_v1",
            "dataset_sha256": _sha256(data_dir / "scam_messages_synthetic.csv"),
            "dataset_rows": len(data),
            "language_values": sorted(data["lang"].unique().tolist()),
            "split_method": comparison["split_method"],
            "seed": seed,
            "calibration": {"method": "platt_scaling", "slope": slope, "intercept": intercept},
            "validation_metrics": {"threshold": threshold, **validation_metrics},
            "test_metrics": model_metrics,
            "model_sha256": _sha256(model_path),
            "mlflow": mlflow_result,
            "limitations": comparison["limitations"],
        }
        (staging / METADATA_FILENAME).write_text(
            json.dumps(metadata, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (staging / COMPARISON_FILENAME).write_text(
            json.dumps(comparison, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staging.rename(output_dir)
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--registered-model-name")
    args = parser.parse_args()
    result = train_synthetic_scam_demo(
        args.data_dir,
        args.output_dir,
        seed=args.seed,
        registered_model_name=args.registered_model_name,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
