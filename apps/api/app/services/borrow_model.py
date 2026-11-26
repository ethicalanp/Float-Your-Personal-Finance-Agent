import hashlib
import hmac
import json
import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import os

    try:
        import sklearn

        sklearn_libs = Path(sklearn.__file__).resolve().parent / ".libs"
        if sklearn_libs.is_dir():
            os.add_dll_directory(str(sklearn_libs))
    except Exception:
        pass

import numpy as np

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableException
from app.models.enums import ReadinessBand
from app.services.borrow_features import FEATURE_COLUMNS, FEATURE_VERSION

MODEL_FORMAT_VERSION = 1
_FEATURE_LABELS = {
    "monthly_inflow_avg": "Average monthly income",
    "income_volatility_cov": "Income volatility",
    "income_sources_count": "Number of income sources",
    "debt_to_income_ratio": "Debt-to-income ratio",
    "expense_to_income_ratio": "Expense-to-income ratio",
    "fixed_expense_ratio": "Fixed-expense ratio",
    "savings_rate_pct": "Savings rate",
    "buffer_runway_months": "Savings runway",
    "min_balance_ratio": "Minimum-balance ratio",
    "negative_balance_events": "Negative-balance events",
}


@lru_cache(maxsize=2)
def _load_model(model_dir: str) -> tuple[Any, dict[str, Any], Any]:
    directory = Path(model_dir).expanduser().resolve()
    model_path = directory / "model.txt"
    metadata_path = directory / "metadata.json"
    if not model_path.is_file() or not metadata_path.is_file():
        raise ServiceUnavailableException(
            "The borrow assessment model is not configured. Train a model on approved, "
            "cash-flow-labeled data and set PFA_BORROW_MODEL_PATH."
        )

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceUnavailableException(f"Unable to read borrow model metadata from {metadata_path}") from exc

    format_version = metadata.get("model_format_version") or metadata.get("artifact_format_version")
    if format_version != MODEL_FORMAT_VERSION:
        raise ServiceUnavailableException("The configured borrow model artifact format is unsupported.")
    if metadata.get("feature_version") != FEATURE_VERSION:
        raise ServiceUnavailableException(
            f"Borrow model feature version {metadata.get('feature_version')!r} "
            f"does not match API feature version {FEATURE_VERSION!r}."
        )
    if metadata.get("feature_columns") != list(FEATURE_COLUMNS):
        raise ServiceUnavailableException("Borrow model feature columns do not match the API feature contract.")

    expected_hash = metadata.get("model_sha256")
    actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if not expected_hash or not hmac.compare_digest(expected_hash, actual_hash):
        raise ServiceUnavailableException("Borrow model artifact checksum validation failed.")

    try:
        import lightgbm as lgb
    except (ImportError, OSError) as exc:
        raise ServiceUnavailableException(
            "The LightGBM runtime is unavailable. Install the API's declared dependencies."
        ) from exc

    booster = lgb.Booster(model_file=str(model_path))
    if booster.num_feature() != len(FEATURE_COLUMNS):
        raise RuntimeError("Loaded LightGBM feature count does not match the API feature contract.")
    try:
        f_names = booster.feature_name()
        if f_names and f_names != list(FEATURE_COLUMNS):
            if not all(name.startswith("Column_") for name in f_names):
                raise RuntimeError("Loaded LightGBM feature names do not match the API feature contract.")
    except (OSError, RuntimeError) as exc:
        if isinstance(exc, RuntimeError) and "contract" in str(exc):
            raise

    try:
        import shap
    except ImportError as exc:
        raise ServiceUnavailableException(
            "SHAP is required to explain borrow assessments. Install the API's declared dependencies."
        ) from exc

    return booster, metadata, shap.TreeExplainer(booster)


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-min(value, 709.0)))
    exp_value = math.exp(max(value, -709.0))
    return exp_value / (1.0 + exp_value)


def _explanation_values(explanation: Any) -> np.ndarray:
    if isinstance(explanation, list):
        explanation = explanation[-1]
    values = np.asarray(explanation)
    if values.ndim == 3:
        values = values[0, :, -1]
    elif values.ndim == 2:
        values = values[0]
    if values.ndim != 1 or len(values) != len(FEATURE_COLUMNS):
        raise RuntimeError("SHAP returned an explanation with an unexpected shape.")
    return values.astype(float)


def _factor(
    feature: str,
    value: Any,
    impact: float,
) -> dict[str, Any]:
    reduces_risk = impact < 0
    return {
        "feature": feature,
        "label": _FEATURE_LABELS[feature],
        "value": float(value) if value is not None else None,
        "impact": round(impact, 6),
        "direction": "positive" if reduces_risk else "negative",
        "description": (
            f"{_FEATURE_LABELS[feature]} contributes toward lower model-estimated risk."
            if reduces_risk
            else f"{_FEATURE_LABELS[feature]} contributes toward higher model-estimated risk."
        ),
    }


def evaluate_borrow_readiness(
    features: dict[str, Any],
    model_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run calibrated LightGBM inference and explain the default-risk log-odds with TreeSHAP."""
    settings = get_settings()
    configured_path = model_dir if model_dir is not None else settings.borrow_model_path
    if not configured_path:
        raise ServiceUnavailableException(
            "The borrow assessment model is not configured. Train a model on approved, "
            "cash-flow-labeled data and set PFA_BORROW_MODEL_PATH."
        )

    booster, metadata, explainer = _load_model(str(Path(configured_path).expanduser().resolve()))
    if features.get("feature_version") != FEATURE_VERSION:
        raise RuntimeError("Extracted borrow features do not match the supported feature version.")

    row_values = []
    for column in FEATURE_COLUMNS:
        value = features.get(column)
        if value is None:
            row_values.append(np.nan)
            continue
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"Borrow feature {column!r} must be finite or None.")
        row_values.append(numeric_value)

    row = np.asarray([row_values], dtype=float)
    raw_score = float(booster.predict(row, raw_score=True)[0])
    calibration = metadata["calibration"]
    calibrated_logit = float(calibration["slope"]) * raw_score + float(calibration["intercept"])
    default_probability = _sigmoid(calibrated_logit)

    shap_values = _explanation_values(explainer.shap_values(row))
    factors = [
        _factor(column, features.get(column), float(impact))
        for column, impact in zip(FEATURE_COLUMNS, shap_values, strict=True)
    ]
    positive_factors = sorted(
        (factor for factor in factors if factor["impact"] < 0),
        key=lambda factor: abs(factor["impact"]),
        reverse=True,
    )[:3]
    negative_factors = sorted(
        (factor for factor in factors if factor["impact"] > 0),
        key=lambda factor: abs(factor["impact"]),
        reverse=True,
    )[:3]

    if default_probability <= 0.12:
        readiness_band = ReadinessBand.STRONG
    elif default_probability <= 0.25:
        readiness_band = ReadinessBand.GOOD
    elif default_probability <= 0.45:
        readiness_band = ReadinessBand.FAIR
    else:
        readiness_band = ReadinessBand.LOW

    return {
        "model_version": metadata["model_version"],
        "feature_version": metadata["feature_version"],
        "default_probability": round(default_probability, 4),
        "readiness_band": readiness_band,
        "top_factors": positive_factors + negative_factors,
        "positive_factors": positive_factors,
        "negative_factors": negative_factors,
    }


def clear_model_cache() -> None:
    """Clear cached model bundles after an explicitly managed model deployment."""
    _load_model.cache_clear()
