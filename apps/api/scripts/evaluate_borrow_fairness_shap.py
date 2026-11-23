#!/usr/bin/env python
"""Evaluate TreeSHAP explainability and algorithmic fairness on Home Credit model.

Features:
- TreeSHAP global importance and local borrower instance attribution
- Adverse action reason generation (translating negative SHAP factors into regulatory compliant reasons)
- Fairness assessment across protected attributes:
  * Gender (CODE_GENDER: Female vs Male)
  * Age Group (<30, 30-50, >50)
  * Education Level (Higher Education vs Secondary/Special)
- Metrics: Disparate Impact (Four-Fifths Rule), Equal Opportunity (TPR difference), and False Positive Rate difference
- Exports fairness_report.json and logs to MLflow if available
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


ADVERSE_REASON_MAP = {
    "CREDIT_INCOME_RATIO": "Requested loan amount is high relative to declared annual income.",
    "ANNUITY_INCOME_RATIO": "Estimated loan annuity payment consumes a large share of monthly income.",
    "ANNUITY_CREDIT_RATIO": "High loan repayment rate relative to loan principal.",
    "GOODS_CREDIT_RATIO": "Loan amount exceeds the appraised value of the goods purchased.",
    "EMPLOYED_TO_AGE_RATIO": "Short cumulative employment history relative to age.",
    "INCOME_PER_PERSON": "Low net household income per family member.",
    "AMT_CREDIT": "Total credit requested exceeds typical approval thresholds.",
    "AMT_ANNUITY": "Loan installment amount is too high.",
    "DAYS_EMPLOYED": "Recent job tenure is shorter than required minimums.",
    "DAYS_BIRTH": "Limited credit bureau history or profile maturity.",
    "EXT_SOURCE_1": "Third-party credit score 1 does not meet threshold.",
    "EXT_SOURCE_2": "Third-party credit score 2 does not meet threshold.",
    "EXT_SOURCE_3": "External credit bureau score indicates elevated default risk.",
}


def explain_instance_shap(
    explainer: Any,
    preprocessed_row: np.ndarray,
    feature_names: list[str],
    top_k: int = 3,
) -> dict[str, Any]:
    """Compute local SHAP attribution and map to human-understandable adverse reasons."""
    shap_vals = explainer.shap_values(preprocessed_row)
    if isinstance(shap_vals, list):
        # Binary classifier: shap_vals[1] is default risk log-odds impact
        shap_vals = shap_vals[1]
    if shap_vals.ndim == 2:
        shap_vals = shap_vals[0]

    feature_impacts = list(zip(feature_names, shap_vals, strict=False))

    # Positive SHAP in default-risk log-odds indicates an adverse factor.
    risk_factors = sorted([item for item in feature_impacts if item[1] > 0], key=lambda x: x[1], reverse=True)
    # Positive impact (negative SHAP decreases default risk -> credit booster)
    credit_boosters = sorted([item for item in feature_impacts if item[1] < 0], key=lambda x: x[1])

    adverse_reasons = []
    for feat, impact in risk_factors[:top_k]:
        base_name = feat.split("__")[-1]
        reason_text = ADVERSE_REASON_MAP.get(base_name, f"Factor '{base_name}' contributes to elevated default risk.")
        adverse_reasons.append({"feature": base_name, "impact": float(impact), "reason": reason_text})

    positive_reasons = []
    for feat, impact in credit_boosters[:top_k]:
        base_name = feat.split("__")[-1]
        positive_reasons.append({
            "feature": base_name,
            "impact": float(impact),
            "description": f"Strong performance in '{base_name}' supports credit approval.",
        })

    return {
        "adverse_action_reasons": adverse_reasons,
        "positive_factors": positive_reasons,
    }


def _wilson_interval(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.96
    rate = successes / total
    denominator = 1.0 + z**2 / total
    center = (rate + z**2 / (2 * total)) / denominator
    margin = z * np.sqrt(rate * (1.0 - rate) / total + z**2 / (4 * total**2)) / denominator
    return [round(float(center - margin), 4), round(float(center + margin), 4)]


def compute_fairness_metrics(
    df: pd.DataFrame,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    protected_attribute: str,
) -> dict[str, Any]:
    """Evaluate group metrics with bootstrap uncertainty intervals on held-out data.

    Note: In credit readiness, approval is predicted non-default (y_pred == 0).
    """
    if protected_attribute not in df.columns:
        return {"error": f"Attribute '{protected_attribute}' not found."}
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred = np.asarray(y_pred, dtype=np.int32)
    if len(df) != len(y_true) or len(y_true) != len(y_pred):
        raise ValueError("Protected attributes, labels, and predictions must have equal lengths.")
    if not set(np.unique(y_true)).issubset({0, 1}) or not set(np.unique(y_pred)).issubset({0, 1}):
        raise ValueError("Fairness labels and predictions must be binary.")

    groups = df[protected_attribute].dropna().unique()
    group_stats: dict[str, dict[str, Any]] = {}
    group_samples: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for grp in groups:
        mask = (df[protected_attribute] == grp).to_numpy()
        if not np.any(mask):
            continue

        grp_y_true = y_true[mask]
        grp_y_pred = y_pred[mask]
        total_applicants = len(grp_y_true)

        # Approval = y_pred == 0 (non-default prediction)
        approved_count = int(np.sum(grp_y_pred == 0))
        approval_rate = float(approved_count / max(total_applicants, 1))

        # Non-defaulters who got approved (True Positive Rate for credit approval)
        actual_non_defaulters = int(np.sum(grp_y_true == 0))
        approved_non_defaulters = int(np.sum((grp_y_true == 0) & (grp_y_pred == 0)))
        tpr = float(approved_non_defaulters / max(actual_non_defaulters, 1))

        # Defaulters who mistakenly got approved (False Positive Rate for approval)
        actual_defaulters = int(np.sum(grp_y_true == 1))
        approved_defaulters = int(np.sum((grp_y_true == 1) & (grp_y_pred == 0)))
        fpr = float(approved_defaulters / max(actual_defaulters, 1))

        group_name = str(grp)
        group_stats[group_name] = {
            "applicant_count": total_applicants,
            "actual_non_defaulter_count": actual_non_defaulters,
            "actual_defaulter_count": actual_defaulters,
            "approval_rate": round(approval_rate, 4),
            "approval_rate_ci95": _wilson_interval(approved_count, total_applicants),
            "tpr_approval": round(tpr, 4),
            "tpr_approval_ci95": _wilson_interval(approved_non_defaulters, actual_non_defaulters),
            "fpr_approval": round(fpr, 4),
            "fpr_approval_ci95": _wilson_interval(approved_defaulters, actual_defaulters),
        }
        group_samples[group_name] = (grp_y_true, grp_y_pred)

    eligible_names = [
        name
        for name, stats in group_stats.items()
        if stats["applicant_count"] >= 30
        and stats["actual_non_defaulter_count"] >= 10
        and stats["actual_defaulter_count"] >= 10
    ]
    eligible_groups = [group_stats[name] for name in eligible_names]
    approval_rates = [v["approval_rate"] for v in eligible_groups]
    if len(approval_rates) >= 2 and max(approval_rates) > 0:
        disparate_impact_ratio = float(min(approval_rates) / max(approval_rates))
    else:
        disparate_impact_ratio = None

    tpr_values = [v["tpr_approval"] for v in eligible_groups]
    tpr_max_diff = float(max(tpr_values) - min(tpr_values)) if len(tpr_values) >= 2 else None
    fpr_values = [v["fpr_approval"] for v in eligible_groups]
    fpr_max_diff = float(max(fpr_values) - min(fpr_values)) if len(fpr_values) >= 2 else None
    disparate_impact_interval = None
    tpr_disparity_interval = None
    fpr_disparity_interval = None

    if len(eligible_names) >= 2:
        selected_samples = [group_samples[name] for name in eligible_names]
        rng = np.random.default_rng(2026)
        ratio_samples = []
        tpr_difference_samples = []
        fpr_difference_samples = []
        for _ in range(1000):
            boot_approval_rates = []
            boot_tpr_rates = []
            boot_fpr_rates = []
            for group_y_true, group_y_pred in selected_samples:
                indices = rng.integers(0, len(group_y_true), len(group_y_true))
                boot_y_true = group_y_true[indices]
                boot_y_pred = group_y_pred[indices]
                boot_approval_rates.append(float(np.mean(boot_y_pred == 0)))

                non_defaulter_mask = boot_y_true == 0
                if np.any(non_defaulter_mask):
                    boot_tpr_rates.append(
                        float(np.mean(boot_y_pred[non_defaulter_mask] == 0))
                    )
                defaulter_mask = boot_y_true == 1
                if np.any(defaulter_mask):
                    boot_fpr_rates.append(
                        float(np.mean(boot_y_pred[defaulter_mask] == 0))
                    )

            highest_rate = max(boot_approval_rates)
            if highest_rate > 0:
                ratio_samples.append(min(boot_approval_rates) / highest_rate)
            if len(boot_tpr_rates) == len(selected_samples):
                tpr_difference_samples.append(max(boot_tpr_rates) - min(boot_tpr_rates))
            if len(boot_fpr_rates) == len(selected_samples):
                fpr_difference_samples.append(max(boot_fpr_rates) - min(boot_fpr_rates))

        if ratio_samples:
            disparate_impact_interval = [
                round(float(value), 4)
                for value in np.quantile(ratio_samples, [0.025, 0.975])
            ]
        if tpr_difference_samples:
            tpr_disparity_interval = [
                round(float(value), 4)
                for value in np.quantile(tpr_difference_samples, [0.025, 0.975])
            ]
        if fpr_difference_samples:
            fpr_disparity_interval = [
                round(float(value), 4)
                for value in np.quantile(fpr_difference_samples, [0.025, 0.975])
            ]

    if disparate_impact_interval is None:
        passes_four_fifths_rule = None
    elif disparate_impact_interval[0] >= 0.80:
        passes_four_fifths_rule = True
    elif disparate_impact_interval[1] < 0.80:
        passes_four_fifths_rule = False
    else:
        passes_four_fifths_rule = None

    return {
        "groups": group_stats,
        "disparate_impact_ratio": (
            round(disparate_impact_ratio, 4) if disparate_impact_ratio is not None else None
        ),
        "passes_four_fifths_rule": passes_four_fifths_rule,
        "tpr_max_disparity": round(tpr_max_diff, 4) if tpr_max_diff is not None else None,
        "fpr_max_disparity": round(fpr_max_diff, 4) if fpr_max_diff is not None else None,
        "disparate_impact_ratio_ci95": disparate_impact_interval,
        "tpr_max_disparity_ci95": tpr_disparity_interval,
        "fpr_max_disparity_ci95": fpr_disparity_interval,
        "uncertainty_method": "percentile bootstrap, 1000 resamples; intervals omitted for inadequate groups",
    }


def evaluate_fairness_and_shap(
    model_path: Path,
    threshold_path: Path,
    data_path: Path,
    output_dir: Path,
    sample_size: int | None = None,
    metadata_path: Path | None = None,
) -> dict[str, Any]:
    """Run fairness and SHAP analysis on the exact held-out Home Credit test split."""
    from scripts.train_home_credit import engineer_financial_features

    metadata_path = metadata_path or model_path.parent / "home_credit_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Research metadata is required to reproduce the held-out split: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("artifact_kind") != "home_credit_research" or metadata.get("dataset_status") != "research_only":
        raise ValueError("Fairness and SHAP analysis requires a research-only Home Credit artifact.")
    if not metadata.get("dataset_provenance", {}).get("data_source") or not metadata.get(
        "dataset_provenance", {}
    ).get("terms_reference"):
        raise ValueError("Verified dataset source and terms must be recorded before evaluation.")

    actual_model_hash = _sha256(model_path)
    if not hmac.compare_digest(str(metadata.get("model_sha256", "")), actual_model_hash):
        raise ValueError("Home Credit model checksum does not match its metadata.")
    if not hmac.compare_digest(str(metadata.get("dataset_sha256", "")), _sha256(data_path)):
        raise ValueError("Home Credit dataset checksum does not match the trained artifact.")

    logger.info("Loading model pipeline from %s", model_path)
    pipeline: Pipeline = joblib.load(model_path)

    threshold = 0.5
    if threshold_path.is_file():
        thresh_data = json.loads(threshold_path.read_text(encoding="utf-8"))
        threshold = float(thresh_data.get("threshold", 0.5))
    else:
        raise FileNotFoundError(f"Recorded validation threshold is required: {threshold_path}")
    recorded_threshold = float(metadata["validation_metrics"]["threshold"])
    if threshold != recorded_threshold:
        raise ValueError("Threshold artifact does not match the value recorded in Home Credit metadata.")
    logger.info("Using decision threshold: %.4f", threshold)

    logger.info("Loading dataset from %s and reproducing its recorded sample", data_path)
    df_raw = pd.read_csv(data_path)
    recorded_sample_size = metadata.get("sample_size")
    if sample_size is not None and sample_size != recorded_sample_size:
        raise ValueError("sample_size must match the value recorded in Home Credit metadata.")
    if recorded_sample_size is not None:
        df_raw = df_raw.sample(n=int(recorded_sample_size), random_state=int(metadata["sampling_seed"]))
        df_raw = df_raw.reset_index(drop=True)
    elif len(df_raw) != metadata.get("source_rows"):
        raise ValueError("Source row count differs from the Home Credit training metadata.")
    if len(df_raw) != metadata.get("dataset_rows"):
        raise ValueError("Recreated dataset row count differs from Home Credit training metadata.")
    df_fe = engineer_financial_features(df_raw)

    target_col = "TARGET"
    if target_col not in df_fe.columns:
        raise ValueError("Target column not present in evaluation data.")

    test_indices = metadata.get("test_row_indices")
    if not isinstance(test_indices, list) or not test_indices:
        raise ValueError("Home Credit metadata does not contain held-out test row positions.")
    if any(not isinstance(index, int) or index < 0 or index >= len(df_fe) for index in test_indices):
        raise ValueError("Home Credit metadata contains invalid held-out test row positions.")
    if len(set(test_indices)) != len(test_indices):
        raise ValueError("Home Credit metadata contains duplicate held-out test row positions.")
    x_data = df_fe.drop(columns=[target_col, "SK_ID_CURR"], errors="ignore")
    if x_data.columns.tolist() != metadata.get("feature_columns"):
        raise ValueError("Home Credit feature columns differ from the trained artifact.")
    x_test = x_data.iloc[test_indices]
    y_true = df_fe[target_col].iloc[test_indices].to_numpy(dtype=np.int32)

    logger.info("Generating predictions on %d untouched test rows...", len(x_test))
    y_proba = pipeline.predict_proba(x_test)[:, 1]
    y_pred = (y_proba >= threshold).astype(int)

    df_eval = x_test.copy()
    if "DAYS_BIRTH" in df_eval.columns:
        age_years = df_eval["DAYS_BIRTH"].abs() / 365.25
        df_eval["AGE_GROUP"] = pd.cut(
            age_years,
            bins=[0, 30, 50, 120],
            labels=["<30", "30-50", ">50"],
        ).astype(str)

    fairness_results = {
        "gender_fairness": compute_fairness_metrics(df_eval, y_true, y_pred, "CODE_GENDER"),
        "age_fairness": compute_fairness_metrics(df_eval, y_true, y_pred, "AGE_GROUP"),
        "education_fairness": compute_fairness_metrics(df_eval, y_true, y_pred, "NAME_EDUCATION_TYPE"),
    }

    try:
        import shap
    except ImportError as exc:
        shap_results: dict[str, Any] = {
            "status": "blocked",
            "reason": f"SHAP is unavailable in this environment: {exc}",
        }
    else:
        logger.info("Initializing TreeSHAP on held-out Home Credit rows...")
        preprocessor = pipeline.named_steps["preprocessor"]
        lgb_model = pipeline.named_steps["model"]
        explain_rows = x_test.iloc[: min(500, len(x_test))]
        x_preprocessed = preprocessor.transform(explain_rows)
        feature_names = preprocessor.get_feature_names_out().tolist()
        explainer = shap.TreeExplainer(lgb_model)
        shap_values = explainer.shap_values(x_preprocessed)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]

        mean_abs_shap = np.mean(np.abs(shap_values), axis=0)
        top_indices = np.argsort(mean_abs_shap)[::-1][:15]
        top_global_features = [
            {"feature": feature_names[i], "mean_abs_shap": round(float(mean_abs_shap[i]), 5)}
            for i in top_indices
        ]
        high_risk_idx = int(np.argmax(y_proba[: len(explain_rows)]))
        sample_explanation = explain_instance_shap(
            explainer=explainer,
            preprocessed_row=x_preprocessed[high_risk_idx : high_risk_idx + 1],
            feature_names=feature_names,
            top_k=3,
        )
        shap_results = {
            "status": "completed",
            "top_global_features": top_global_features,
            "sample_high_risk_score": float(y_proba[high_risk_idx]),
            "sample_explanation": sample_explanation,
        }

    report = {
        "dataset_status": "research_only",
        "dataset_provenance": metadata["dataset_provenance"],
        "evaluation_samples": len(x_test),
        "decision_threshold": threshold,
        "fairness_assessment": fairness_results,
        "shap_explainability": shap_results,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "fairness_report.json"
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing fairness report: {report_path}")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Exported fairness & SHAP report to %s", report_path.resolve())

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Fairness and SHAP on Home Credit")
    parser.add_argument("--model-path", type=Path, default=Path("artifacts/home_credit_lightgbm_engineered.joblib"))
    parser.add_argument("--threshold-path", type=Path, default=Path("artifacts/borrow_threshold.json"))
    parser.add_argument("--data-path", type=Path, default=Path("data/raw/application_train.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--metadata-path", type=Path, default=None)
    parser.add_argument("--sample-size", type=int, default=None)

    args = parser.parse_args()
    evaluate_fairness_and_shap(
        model_path=args.model_path,
        threshold_path=args.threshold_path,
        data_path=args.data_path,
        output_dir=args.output_dir,
        sample_size=args.sample_size,
        metadata_path=args.metadata_path,
    )


if __name__ == "__main__":
    main()
