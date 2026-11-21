#!/usr/bin/env python
"""Generate clearly synthetic fixtures for ML data-pipeline smoke tests only."""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.services.borrow_features import FEATURE_COLUMNS, FEATURE_VERSION

DEFAULT_ROW_COUNT = 300
MIN_ROW_COUNT = 100
MAX_ROW_COUNT = 500
DEFAULT_SEED = 2026

_LANGUAGES = ("en", "ml", "manglish")
_VARIANTS = {
    "bank": ("a fictional bank", "a pretend bank", "a demo bank"),
    "amount": ("500", "1200", "2500", "5000", "7500"),
    "reference": ("DEMO-104", "DEMO-218", "DEMO-361", "DEMO-492"),
}
_MESSAGE_TEMPLATES: dict[str, dict[int, tuple[str, ...]]] = {
    "en": {
        1: (
            "SYNTHETIC TEST ONLY: {bank} says the account will be blocked and asks for an OTP.",
            "SYNTHETIC TEST ONLY: a fictional prize claim requests an upfront fee of INR {amount}.",
            "SYNTHETIC TEST ONLY: a fake utility warning threatens disconnection unless INR {amount} is paid.",
            "SYNTHETIC TEST ONLY: a refund message asks the reader to install an unknown support app.",
        ),
        0: (
            "SYNTHETIC TEST ONLY: {bank} says the monthly statement is ready in the official app.",
            "SYNTHETIC TEST ONLY: a receipt confirms the utility bill was paid; reference {reference}.",
            "SYNTHETIC TEST ONLY: a routine salary deposit of INR {amount} is confirmed.",
            "SYNTHETIC TEST ONLY: an appointment reminder gives the time and clinic address.",
        ),
    },
    "ml": {
        1: (
            "SYNTHETIC TEST ONLY: അക്കൗണ്ട് തടയുമെന്ന് പറഞ്ഞ് ഒരു സാങ്കൽപ്പിക സന്ദേശം OTP ആവശ്യപ്പെടുന്നു.",
            "SYNTHETIC TEST ONLY: സമ്മാനം ലഭിക്കാൻ INR {amount} മുൻകൂർ ഫീസ് ചോദിക്കുന്നു.",
            "SYNTHETIC TEST ONLY: വൈദ്യുതി വിച്ഛേദിക്കുമെന്ന് പറഞ്ഞ് INR {amount} ഉടൻ അടയ്ക്കാൻ ആവശ്യപ്പെടുന്നു.",
            "SYNTHETIC TEST ONLY: റീഫണ്ട് ലഭിക്കാൻ അറിയാത്ത ആപ്പ് ഇൻസ്റ്റാൾ ചെയ്യാൻ പറയുന്നു.",
        ),
        0: (
            "SYNTHETIC TEST ONLY: {bank} ആപ്പിൽ മാസ സ്റ്റേറ്റ്മെന്റ് ലഭ്യമാണെന്ന് അറിയിക്കുന്നു.",
            "SYNTHETIC TEST ONLY: വൈദ്യുതി ബിൽ അടച്ചതായി രസീത് സ്ഥിരീകരിക്കുന്നു {reference}.",
            "SYNTHETIC TEST ONLY: INR {amount} ശമ്പളം അക്കൗണ്ടിൽ എത്തിയതായി അറിയിക്കുന്നു.",
            "SYNTHETIC TEST ONLY: ക്ലിനിക്കിലെ അപ്പോയിന്റ്മെന്റ് സമയത്തെക്കുറിച്ചുള്ള ഓർമ്മപ്പെടുത്തൽ.",
        ),
    },
    "manglish": {
        1: (
            "SYNTHETIC TEST ONLY: {bank} account block aakum ennu paranju OTP chodikkunnu.",
            "SYNTHETIC TEST ONLY: fictional prize kittan INR {amount} fee ayakkan parayunnu.",
            "SYNTHETIC TEST ONLY: current cut aakum ennu paranju INR {amount} udan adakkan parayunnu.",
            "SYNTHETIC TEST ONLY: refund kittan unknown support app install cheyyan parayunnu.",
        ),
        0: (
            "SYNTHETIC TEST ONLY: {bank} appil monthly statement ready aanu ennu ariyikkunnu.",
            "SYNTHETIC TEST ONLY: current bill pay cheythu, receipt {reference} ennu confirm cheyyunnu.",
            "SYNTHETIC TEST ONLY: INR {amount} salary accountil credit aayi ennu ariyikkunnu.",
            "SYNTHETIC TEST ONLY: clinic appointment time ormaippikkunna normal notification.",
        ),
    },
}


def _borrow_rows(row_count: int, rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    start_date = date(2024, 1, 1)
    for index in range(row_count):
        features: dict[str, Any] = {
            "monthly_inflow_avg": round(rng.uniform(25_000, 250_000), 2),
            "income_volatility_cov": round(rng.uniform(0.05, 0.9), 4),
            "income_sources_count": rng.randint(1, 4),
            "debt_to_income_ratio": round(rng.uniform(0, 1.2), 4),
            "expense_to_income_ratio": round(rng.uniform(0.2, 1.3), 4),
            "fixed_expense_ratio": round(rng.uniform(0.1, 0.9), 4),
            "savings_rate_pct": round(rng.uniform(-30, 60), 2),
            "buffer_runway_months": round(rng.uniform(0, 24), 2),
            "min_balance_ratio": "",
            "negative_balance_events": "",
        }
        risk = (
            0.27 * min(features["debt_to_income_ratio"], 1.2) / 1.2
            + 0.25 * min(features["expense_to_income_ratio"], 1.3) / 1.3
            + 0.18 * features["fixed_expense_ratio"]
            + 0.12 * features["income_volatility_cov"] / 0.9
            + 0.10 * max(0.0, 30.0 - features["savings_rate_pct"]) / 90.0
            + 0.08 / (features["buffer_runway_months"] + 1.0)
        )
        rows.append(
            {
                "synthetic_user_id": f"synthetic-user-{index + 1:04d}",
                "as_of_date": (start_date + timedelta(days=index * 2)).isoformat(),
                "synthetic_risk_score": round(risk, 6),
                **features,
            }
        )
    threshold = sorted(row["synthetic_risk_score"] for row in rows)[len(rows) // 2]
    for row in rows:
        row["synthetic_target_default"] = int(row["synthetic_risk_score"] >= threshold)
    return rows


def _scam_rows(row_count: int, rng: random.Random) -> list[dict[str, Any]]:
    rows = []
    templates = [
        (language, label, template_index, template)
        for language in _LANGUAGES
        for label in (0, 1)
        for template_index, template in enumerate(_MESSAGE_TEMPLATES[language][label])
    ]
    for index in range(row_count):
        language, label, template_index, template = templates[index % len(templates)]
        text = template.format(
            bank=rng.choice(_VARIANTS["bank"]),
            amount=rng.choice(_VARIANTS["amount"]),
            reference=rng.choice(_VARIANTS["reference"]),
        )
        rows.append(
            {
                "synthetic_message_id": f"synthetic-message-{index + 1:04d}",
                "text": text,
                "synthetic_is_scam": label,
                "lang": language,
                "template_group": f"{language}-{label}-{template_index}",
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate_synthetic_datasets(
    output_dir: Path,
    *,
    row_count: int = DEFAULT_ROW_COUNT,
    seed: int = DEFAULT_SEED,
    force: bool = False,
) -> dict[str, Path]:
    """Write synthetic Borrow and scam fixtures that cannot match the real-label columns."""
    if not MIN_ROW_COUNT <= row_count <= MAX_ROW_COUNT:
        raise ValueError(f"row_count must be between {MIN_ROW_COUNT} and {MAX_ROW_COUNT}.")

    output_dir = output_dir.expanduser().resolve()
    borrow_path = output_dir / "borrow_features_synthetic.csv"
    scam_path = output_dir / "scam_messages_synthetic.csv"
    manifest_path = output_dir / "synthetic_dataset_manifest.json"
    output_paths = (borrow_path, scam_path, manifest_path)
    existing_paths = [path for path in output_paths if path.exists()]
    if existing_paths and not force:
        raise FileExistsError(
            "Refusing to overwrite synthetic data; pass --force to replace: "
            + ", ".join(str(path) for path in existing_paths)
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    borrow_rows = _borrow_rows(row_count, rng)
    scam_rows = _scam_rows(row_count, rng)
    _write_csv(borrow_path, borrow_rows)
    _write_csv(scam_path, scam_rows)

    manifest = {
        "dataset_status": "synthetic_pipeline_test_only",
        "row_count_per_file": row_count,
        "random_seed": seed,
        "borrow_feature_version": FEATURE_VERSION,
        "borrow_feature_columns": list(FEATURE_COLUMNS),
        "borrow_label_column": "synthetic_target_default",
        "borrow_target_rule": (
            "The median split of the documented weighted synthetic_risk_score; "
            "this is a toy scenario label, not a real outcome."
        ),
        "scam_label_column": "synthetic_is_scam",
        "scam_template_groups": 24,
        "scam_split_group_column": "template_group",
        "limitations": [
            "All rows, feature values, messages, and labels are invented.",
            "Training and metrics are only for verifying the isolated demo pipeline.",
            "Metrics do not establish real-world predictive quality, calibration, or fairness.",
            "These files are not approved cohort data and are not a substitute for licensed scam messages.",
            "Synthetic label names intentionally differ from the production trainer's expected labels.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "borrow": borrow_path,
        "scam": scam_path,
        "manifest": manifest_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROW_COUNT, help="Rows per fixture (100-500).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "synthetic_ml_v2",
        help="Output directory; generated files should remain outside Git.",
    )
    parser.add_argument("--force", action="store_true", help="Replace files in the output directory.")
    args = parser.parse_args()

    paths = generate_synthetic_datasets(
        args.output_dir,
        row_count=args.rows,
        seed=args.seed,
        force=args.force,
    )
    print(json.dumps({name: str(path) for name, path in paths.items()}, indent=2))


if __name__ == "__main__":
    main()
