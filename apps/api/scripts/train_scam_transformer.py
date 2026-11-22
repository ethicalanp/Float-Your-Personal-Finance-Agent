#!/usr/bin/env python
"""Report transformer prerequisites without training on unapproved sample data."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def check_gpu_and_dependencies() -> dict[str, Any]:
    """Inspect PyTorch, CUDA GPU capability, and HuggingFace Transformers availability."""
    status: dict[str, Any] = {
        "torch_installed": False,
        "cuda_available": False,
        "gpu_name": None,
        "transformers_installed": False,
    }
    try:
        import torch

        status["torch_installed"] = True
        status["cuda_available"] = bool(torch.cuda.is_available())
        if status["cuda_available"]:
            status["gpu_name"] = str(torch.cuda.get_device_name(0))
    except ImportError:
        pass

    try:
        import transformers  # noqa: F401

        status["transformers_installed"] = True
    except ImportError:
        pass

    return status


def run_transformer_experiment(
    output_dir: Path,
    model_name: str = "google/muril-base-cased",
) -> dict[str, Any]:
    """Record that training is blocked until licensed data and held-out splits are available."""
    dep_status = check_gpu_and_dependencies()
    logger.info("Environment status: %s", dep_status)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "scam_transformer_benchmark.json"
    result = {
        "model_name": model_name,
        "status": "not_run",
        "reason": "Licensed labeled scam data and leakage-resistant evaluation splits are unavailable.",
        "environment": dep_status,
    }

    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("Saved transformer experiment report to %s", report_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Multilingual Transformer Scam Experiment")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--model-name", type=str, default="google/muril-base-cased")
    args = parser.parse_args()
    run_transformer_experiment(output_dir=args.output_dir, model_name=args.model_name)


if __name__ == "__main__":
    main()
