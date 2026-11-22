#!/usr/bin/env python
"""Run one local inference using the isolated synthetic scam demo artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.synthetic_scam_demo import evaluate_synthetic_scam_demo
from scripts.train_synthetic_scam_demo import DEFAULT_OUTPUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--message-file", type=Path, required=True)
    args = parser.parse_args()
    message = args.message_file.read_text(encoding="utf-8")
    print(json.dumps(evaluate_synthetic_scam_demo(message, args.model_dir), indent=2))


if __name__ == "__main__":
    main()
