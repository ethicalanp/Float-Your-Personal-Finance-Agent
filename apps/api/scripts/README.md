# Borrow-readiness model training

The API does not train a model during requests. Train and review a versioned
artifact offline, then configure `PFA_BORROW_MODEL_PATH` to its directory.

## Training data contract

Provide one point-in-time row per pseudonymous user in CSV. `as_of_date` is the
date at which the features were known. `target_default` is 0 or 1 for an
explicitly defined future outcome window after that date. Do not include
identifiers, transaction descriptions, account numbers, or other direct PII.

Required columns:

```text
user_id,as_of_date,target_default,monthly_inflow_avg,income_volatility_cov,
income_sources_count,debt_to_income_ratio,expense_to_income_ratio,
fixed_expense_ratio,savings_rate_pct,buffer_runway_months,min_balance_ratio,
negative_balance_events
```

All feature columns are numeric. Empty cells mean unavailable, not zero; the
LightGBM model handles missing values. The feature schema and ordering are
versioned in `app.services.borrow_features`. The current account schema has no
historical balance series, so `min_balance_ratio` and `negative_balance_events`
are unavailable from the API and should remain blank until verified balance
history is collected. Version `v1.1.0` only aggregates INR accounts and counts
categorized earned income; transfers, refunds, reversals, and cashback are
excluded from inflow. These definitions must also be used when preparing labels'
feature rows.

The trainer rejects repeat rows per user, groups observations by date, and
requires a chronological span long enough for four partitions and three
label-horizon embargo gaps. It uses separate fit, early-stopping, calibration,
and test windows, fits Platt calibration on the calibration window, and reports
ROC-AUC, average precision, Brier score, log loss, and test default rate. Review dataset provenance, target
definition, sample sizes, calibration, and subgroup performance before using an
artifact. Passing training code or a high metric alone does not establish
production suitability.

## Train and configure

From `apps/api`, install the declared API dependencies and run:

```powershell
python -m scripts.train_borrow_model `
  --csv D:\approved-data\borrow-features.csv `
  --output artifacts\borrow\v1.1.0 `
  --data-source "approved cash-flow outcome cohort" `
  --label-horizon-days 90 `
  --model-version v1.1.0
```

The output directory must not already exist. Review the printed test metrics
and `metadata.json`, then set:

```dotenv
PFA_BORROW_MODEL_PATH=artifacts/borrow/v1.1.0
```

The API verifies the model checksum and exact feature version before inference.
Without a configured compatible artifact, assessment requests return a clear
503 response instead of a fallback score.

---

# ML research pipelines and data gates

These experiments are separate from the serving APIs. Home Credit artifacts are
not compatible with the cash-flow Borrow model and must never be configured as
`PFA_BORROW_MODEL_PATH`. Do not treat results from handcrafted seed messages or
synthetic fixtures as real-data model evidence.

### 1. Home Credit research benchmark

This is a research-only LightGBM pipeline for the Home Credit target, not a
production Borrow model. The script records the dataset source and terms
reference, uses stratified train/calibration/validation/test splits, calibrates
probabilities, and selects the threshold on validation data. MLflow tracking
and registration are optional and require a configured backend.

The local `application_train.csv` and `application_test.csv` SHA-256 values
match the respective files in the
[Rohanerk Hugging Face mirror](https://huggingface.co/datasets/Rohanerk/home-credit-default-risk/tree/a046610bcfef461dc7f9c809813bf91b3e071970),
whose dataset card declares MIT. This is a third-party mirror; the original
Home Credit/Kaggle terms were not independently located. Keep this track
research-only and review upstream rights before redistribution or promotion.

```powershell
python -m scripts.train_home_credit `
  --data-path ..\..\data\raw\application_train.csv `
  --output-dir ..\..\artifacts\home_credit_research\v1 `
  --data-source "Hugging Face Rohanerk/home-credit-default-risk revision a046610bcfef461dc7f9c809813bf91b3e071970" `
  --terms-reference "MIT declared by the Hugging Face dataset card at revision a046610bcfef461dc7f9c809813bf91b3e071970; original upstream terms require separate review"
```

The local full training CSV (307,511 rows) has SHA-256
`52e96b895b1112e1c853f670e58372719c8441c5ed1c57ac2f7fad559d784f5f`, matching
the mirror's LFS hash. The current untouched test split has 46,127 rows. Results:
ROC-AUC 0.7689, PR-AUC 0.2582 (constant-rate baseline 0.0807), precision 0.2581,
recall 0.4168, F1 0.3188, and Brier score 0.0672 (baseline 0.0742), at the
validation-selected threshold 0.1657. MLflow was not configured, so no run or
registry ID exists. These are research benchmark results only; the upstream
license caveat remains, and this artifact must not be used by Borrow serving.

Exports:
- `artifacts/home_credit_research/v1/home_credit_lightgbm_engineered.joblib`
- `artifacts/home_credit_research/v1/borrow_threshold.json`
- `artifacts/home_credit_research/v1/home_credit_metadata.json`

### 2. Exploratory SHAP and fairness analysis

Run this only against the exact untouched test partition recorded in the
Home Credit artifact metadata. The script verifies dataset/model checksums and
the recorded test row positions. It reports fairness metrics with bootstrap
95% uncertainty intervals for gender (`CODE_GENDER`), age brackets, and
education levels. Inadequate group/class counts or an interval crossing 0.80
produce an indeterminate Four-Fifths result, not a pass. On the current 46,127
row held-out test split, SHAP completed. Age-group disparate impact was 0.3118
(95% bootstrap CI 0.2829–0.3435); gender was 0.5670 and education was 0.2765.
All are below 0.80, and this is not a fairness approval. The report includes
group counts and uncertainty intervals; it is a research finding requiring
documented review, not a basis to deploy or adjust the model.

```powershell
python -m scripts.evaluate_borrow_fairness_shap `
  --model-path ..\..\artifacts\home_credit_research\v1\home_credit_lightgbm_engineered.joblib `
  --threshold-path ..\..\artifacts\home_credit_research\v1\borrow_threshold.json `
  --metadata-path ..\..\artifacts\home_credit_research\v1\home_credit_metadata.json `
  --data-path ..\..\data\raw\application_train.csv `
  --output-dir ..\..\artifacts\home_credit_research\v1\fairness_run_1
```

Exports `artifacts/home_credit_research/v1/fairness_run_1/fairness_report.json`
with held-out group metrics, bootstrap intervals, and SHAP explanations.

### 3. Real scam-model status

Real TF-IDF evaluation is blocked until a sufficiently large, licensed,
multilingual labeled corpus is supplied. No real-scam model is trained or
integrated; the production endpoint continues to use the deterministic rule
baseline. The synthetic scam demo below tests the pipeline only and is not a
substitute for a real-data benchmark.

### 4. Transformer prerequisite report

The command reports `not_run`; it does not fine-tune or produce benchmark
figures. Fine-tuning requires approved labeled data, separate train/validation/
test splits, and suitable compute.

```powershell
python -m scripts.train_scam_transformer `
  --output-dir ..\..\artifacts
```

### Synthetic pipeline-test fixtures

Generate up to 500 explicitly synthetic rows per fixture for isolated
experimental-model demos:

```powershell
python -m scripts.generate_synthetic_ml_data --rows 500
```

By default, new files are written under the ignored
`apps/api/artifacts/synthetic_ml_v2/` directory. Existing generated files are
never overwritten. The labels are named `synthetic_*`; Borrow labels are
derived from a documented toy risk formula, and scam text uses template groups
for leakage-resistant synthetic splits. These experiments demonstrate the
training and inference pipeline only. Metrics describe the invented data
distribution and must not be presented as real-world accuracy, fairness, or
financial decision evidence. Home Credit and real-world scam claims require
separate provenance and evaluation.

### Isolated synthetic demo models

The two demo trainers use only the generated v2 fixtures and write immutable,
checksummed artifacts:

```powershell
python -m scripts.train_synthetic_borrow_demo
python -m scripts.train_synthetic_scam_demo
```

Both use separate training, calibration, validation, and test partitions. The
scam demo keeps `template_group` disjoint across partitions and compares TF-IDF
with the deterministic rule baseline. These figures are pipeline smoke-test
results only; synthetic data cannot establish real-world model quality.

The local predictors are `scripts.predict_synthetic_borrow_demo` (accepts a
JSON object containing `feature_version` and the exact `v1.1.0` feature fields)
and `scripts.predict_synthetic_scam_demo` (reads message text from a local
file and does not print or store it). Their outputs remain synthetic-only.

To expose the demos in Swagger, explicitly enable them and configure each path:

```dotenv
PFA_ENABLE_SYNTHETIC_ML_DEMOS=true
PFA_SYNTHETIC_BORROW_DEMO_MODEL_PATH=artifacts/synthetic_ml_v2/borrow_model_lightgbm
PFA_SYNTHETIC_SCAM_DEMO_MODEL_PATH=artifacts/synthetic_ml_v2/scam_model
```

Use `POST /api/v1/ml-demo/borrow` and `POST /api/v1/ml-demo/scam`. Both require
authentication and AI-processing consent. A missing model returns 503; neither
route falls back to rules or to the production Borrow artifact. The Borrow
production route remains gated on an approved real cash-flow cohort, and the
demo routes do not persist submitted features or messages. Disable the demos
and remove these paths outside the local showcase environment.
