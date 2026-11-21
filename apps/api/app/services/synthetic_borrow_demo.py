import hashlib
import hmac
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import sklearn  # noqa: F401

from app.core.errors import ServiceUnavailableException
from app.services.borrow_features import FEATURE_COLUMNS, FEATURE_VERSION

MODEL_FORMAT_VERSION = 1


@lru_cache(maxsize=2)
def _load_model(model_dir: str) -> tuple[Any, dict[str, Any]]:
    directory = Path(model_dir).expanduser().resolve()
    model_path = directory / "model.txt"
    metadata_path = directory / "metadata.json"
    if not model_path.is_file() or not metadata_path.is_file():
        raise ServiceUnavailableException(
            "The synthetic Borrow demo model is unavailable. Configure a trained demo artifact."
        )

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read synthetic Borrow demo metadata from {metadata_path}") from exc

    if metadata.get("artifact_format_version") != MODEL_FORMAT_VERSION:
        raise RuntimeError("The synthetic Borrow demo artifact format is unsupported.")
    if metadata.get("artifact_kind") != "synthetic_borrow_demo" or metadata.get("dataset_status") != "synthetic_only":
        raise RuntimeError("The configured artifact is not an explicitly synthetic Borrow demo model.")
    if metadata.get("feature_version") != FEATURE_VERSION:
        raise RuntimeError("Synthetic Borrow demo feature version does not match the API contract.")
    if metadata.get("feature_columns") != list(FEATURE_COLUMNS):
        raise RuntimeError("Synthetic Borrow demo feature columns do not match the API contract.")

    expected_hash = metadata.get("model_sha256")
    actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if not expected_hash or not hmac.compare_digest(expected_hash, actual_hash):
        raise RuntimeError("Synthetic Borrow demo model checksum validation failed.")

    try:
        import lightgbm as lgb
    except (ImportError, OSError) as exc:
        raise ServiceUnavailableException(
            "The LightGBM runtime is unavailable for the synthetic Borrow demo."
        ) from exc

    model = lgb.Booster(model_file=str(model_path))
    if model.num_feature() != len(FEATURE_COLUMNS):
        raise RuntimeError("Synthetic Borrow demo model has an unexpected feature count.")
    return model, metadata


def evaluate_synthetic_borrow_demo(
    features: dict[str, Any],
    model_dir: str | Path | None,
) -> dict[str, Any]:
    """Return an educational prediction from an isolated synthetic-only artifact."""
    if not model_dir:
        raise ServiceUnavailableException(
            "The synthetic Borrow demo model is not configured. Set its explicit artifact path to enable the demo."
        )
    if features.get("feature_version") != FEATURE_VERSION:
        raise ValueError(f"Synthetic Borrow demo requires feature version {FEATURE_VERSION}.")

    row: list[float] = []
    for column in FEATURE_COLUMNS:
        value = features.get(column)
        if value is None:
            row.append(float("nan"))
            continue
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError(f"Borrow feature {column!r} must be finite or None.")
        row.append(numeric_value)

    model, metadata = _load_model(str(Path(model_dir).expanduser().resolve()))
    raw_probability = float(model.predict(np.asarray([row], dtype=float))[0])
    calibration = metadata["calibration"]
    clipped = min(max(raw_probability, 1e-6), 1.0 - 1e-6)
    logit = math.log(clipped / (1.0 - clipped))
    calibrated_logit = float(calibration["slope"]) * logit + float(calibration["intercept"])
    calibrated_probability = 1.0 / (1.0 + math.exp(-max(min(calibrated_logit, 709.0), -709.0)))
    threshold = float(metadata["validation_metrics"]["threshold"])
    return {
        "model_track": "synthetic_borrow_demo",
        "model_version": metadata["model_version"],
        "feature_version": FEATURE_VERSION,
        "synthetic_default_probability": round(calibrated_probability, 4),
        "demo_flag": calibrated_probability >= threshold,
        "demo_threshold": threshold,
        "warning": "Synthetic-only educational demo; not a real default-risk estimate or lending decision.",
    }


def clear_model_cache() -> None:
    """Clear cached demo artifacts after an explicitly managed local change."""
    _load_model.cache_clear()
