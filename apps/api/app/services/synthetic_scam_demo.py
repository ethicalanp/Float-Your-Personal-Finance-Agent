import hashlib
import hmac
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib

from app.core.errors import ServiceUnavailableException

MODEL_FORMAT_VERSION = 1


@lru_cache(maxsize=2)
def _load_model(model_dir: str) -> tuple[Any, dict[str, Any]]:
    directory = Path(model_dir).expanduser().resolve()
    model_path = directory / "model.joblib"
    metadata_path = directory / "metadata.json"
    if not model_path.is_file() or not metadata_path.is_file():
        raise ServiceUnavailableException(
            "The synthetic scam demo model is unavailable. Configure a trained demo artifact."
        )

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read synthetic scam demo metadata from {metadata_path}") from exc

    if metadata.get("artifact_format_version") != MODEL_FORMAT_VERSION:
        raise RuntimeError("The synthetic scam demo artifact format is unsupported.")
    if metadata.get("artifact_kind") != "synthetic_scam_demo" or metadata.get("dataset_status") != "synthetic_only":
        raise RuntimeError("The configured artifact is not an explicitly synthetic scam demo model.")
    if metadata.get("model_version") != "synthetic_scam_demo_v1":
        raise RuntimeError("The configured synthetic scam model version is unsupported.")

    expected_hash = metadata.get("model_sha256")
    actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if not isinstance(expected_hash, str) or not hmac.compare_digest(expected_hash, actual_hash):
        raise RuntimeError("Synthetic scam demo model checksum validation failed.")

    model = joblib.load(model_path)
    if list(getattr(model, "classes_", [])) != [0, 1] or not callable(getattr(model, "predict_proba", None)):
        raise RuntimeError("Synthetic scam demo model does not expose binary probability inference.")
    return model, metadata


def evaluate_synthetic_scam_demo(message: str, model_dir: str | Path | None) -> dict[str, Any]:
    """Return a synthetic-only scam probability without storing or returning the message."""
    if not message.strip():
        raise ValueError("Message must not be empty.")
    if len(message) > 5000:
        raise ValueError("Message must be at most 5000 characters.")
    if not model_dir:
        raise ServiceUnavailableException(
            "The synthetic scam demo model is not configured. Set its explicit artifact path to enable the demo."
        )

    model, metadata = _load_model(str(Path(model_dir).expanduser().resolve()))
    raw_probability = float(model.predict_proba([message])[0, 1])
    calibration = metadata["calibration"]
    clipped = min(max(raw_probability, 1e-6), 1.0 - 1e-6)
    logit = math.log(clipped / (1.0 - clipped))
    calibrated_logit = float(calibration["slope"]) * logit + float(calibration["intercept"])
    probability = 1.0 / (1.0 + math.exp(-max(min(calibrated_logit, 709.0), -709.0)))
    threshold = float(metadata["validation_metrics"]["threshold"])
    return {
        "model_track": "synthetic_scam_demo",
        "model_version": metadata["model_version"],
        "synthetic_scam_probability": round(probability, 4),
        "demo_flag": probability >= threshold,
        "demo_threshold": threshold,
        "warning": "Synthetic-only educational demo; not validated for real scam detection.",
    }


def clear_model_cache() -> None:
    """Clear cached demo artifacts after an explicitly managed local change."""
    _load_model.cache_clear()
