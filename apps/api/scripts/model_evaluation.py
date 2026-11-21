"""Shared binary-classification calibration and evaluation utilities."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


def _logit(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1.0 - 1e-6)
    logits = np.asarray(np.log(clipped / (1.0 - clipped)), dtype=np.float64)
    return logits.reshape(-1, 1)


def fit_platt_calibration(
    probabilities: np.ndarray,
    labels: np.ndarray,
) -> tuple[float, float]:
    """Fit a Platt transform on a separate calibration partition."""
    calibrator = LogisticRegression(C=1e6, max_iter=1000, solver="lbfgs")
    calibrator.fit(_logit(probabilities), labels)
    slope = float(calibrator.coef_[0][0])
    intercept = float(calibrator.intercept_[0])
    if slope <= 0:
        raise ValueError("Calibration learned a non-positive risk slope.")
    return slope, intercept


def apply_platt_calibration(
    probabilities: np.ndarray,
    slope: float,
    intercept: float,
) -> np.ndarray:
    logits = slope * _logit(probabilities).reshape(-1) + intercept
    logits = np.clip(logits, -709.0, 709.0)
    return 1.0 / (1.0 + np.exp(-logits))


def select_f1_threshold(
    labels: np.ndarray,
    probabilities: np.ndarray,
) -> tuple[float, dict[str, float]]:
    """Select a classification threshold on validation data only."""
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    if not len(thresholds):
        raise ValueError("Threshold selection requires both classes in validation data.")
    f1_scores = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    best_index = int(np.argmax(f1_scores))
    threshold = float(thresholds[best_index])
    return threshold, {
        "precision": float(precision[best_index]),
        "recall": float(recall[best_index]),
        "f1": float(f1_scores[best_index]),
    }


def binary_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    """Report ranking, threshold, and calibration metrics on an untouched partition."""
    labels = np.asarray(labels, dtype=np.int32)
    probabilities = np.asarray(probabilities, dtype=float)
    predictions = (probabilities >= threshold).astype(np.int32)
    bin_edges = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    for lower, upper in zip(bin_edges[:-1], bin_edges[1:], strict=True):
        mask = (probabilities >= lower) & (
            probabilities < upper if upper < 1.0 else probabilities <= upper
        )
        if np.any(mask):
            ece += float(np.mean(mask)) * abs(float(np.mean(probabilities[mask])) - float(np.mean(labels[mask])))

    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "expected_calibration_error_10_bins": ece,
        "positive_rate": float(np.mean(labels)),
        "threshold": float(threshold),
        "rows": int(len(labels)),
    }
