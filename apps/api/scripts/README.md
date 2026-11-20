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
