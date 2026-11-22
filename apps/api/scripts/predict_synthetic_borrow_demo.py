#!/usr/bin/env python
"""Run one local inference using the isolated synthetic Borrow demo artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.services.synthetic_borrow_demo import evaluate_synthetic_borrow_demo
from scripts.train_synthetic_borrow_demo import DEFAULT_OUTPUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--features-json", type=Path, required=True)
    args = parser.parse_args()
    features: Any = json.loads(args.features_json.read_text(encoding="utf-8"))
    if not isinstance(features, dict):
        raise ValueError("The features JSON must contain a single object.")
    print(json.dumps(evaluate_synthetic_borrow_demo(features, args.model_dir), indent=2))


if __name__ == "__main__":
    main()
