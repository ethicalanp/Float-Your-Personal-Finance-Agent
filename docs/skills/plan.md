# Budget Plan & Recurring Payments Skill

## Educational Only
- Float provides budgeting, cash-flow tracking, and bill reminders for educational and personal planning purposes only.
- Never provide investment advice, stock/fund recommendations, or personalized portfolio allocation guidance.

## Budget Plan Rules
- **Currency & Precision**: Store all monetary values in INR paise (`int` / `BigInteger`, 1 INR = 100 paise). All calculations use integer paise or `Decimal`; never use float arithmetic for money.
- **Income Modes**:
  - `fixed`: monthly take-home income + optional extra income.
  - `irregular_avg`: average monthly inflow over the last N months (default 3, bounded 1–12) from imported credit transactions.
  - `irregular_conservative`: user-entered conservative baseline income.
  - Validation: total income > 0, sane upper bound (<= ₹100 crore / 10^10 paise), percentages each >= 0 and sum strictly to 100.00%.
- **Splits & Rounding**:
  - Default split: `50 / 30 / 20` (needs / wants / savings). Presets include `50/30/20`, `60/20/20`, `50/20/30`.
  - Users can edit percentages or amounts directly (sliders + numeric inputs stay synced).
  - Allocate paise using the **largest-remainder method** so `needs_paise + wants_paise + savings_paise == total_income_paise` exactly.
  - Per-category mapping to `needs` / `wants` / `savings` is user-editable (e.g., `Rent & Housing` -> `needs`).
- **Versioning & Concurrency**:
  - Plans are versioned per calendar month using **IST (`Asia/Kolkata`)** month boundaries (`YYYY-MM`).
  - Edits use optimistic concurrency (`expected_version` -> `409 Conflict` if stale); full version history is readable.
  - Deterministic calculations only — no LLM math.
- **Plan vs Actual & Warnings**:
  - Compare planned buckets against actual spending from imported transactions when present; never invent data when a month has no transactions.
  - Emit deterministic warnings when `active_recurring_needs + actual_needs > needs_budget` or `> total_income`.
- **Privacy & Sensitivity**:
  - Treat income as sensitive: never log raw income amounts, include budget plans in DPDP export, purge on account deletion, and mask before any external LLM call.

## Recurring Payments Rules
- **Commitments**: Support `weekly`, `monthly`, `quarterly`, `yearly` frequencies; fixed amount or `min_amount`–`max_amount` range; `due_rule_day` (1–31, clamped to month-end e.g. Feb 28/29, Apr 30); `category` (`rent`, `EMI`, `SIP`, `insurance`, `subscription`, `utilities`, `other`, or display labels); `merchant` + `merchant_keywords`; `start_date` / `end_date`; `is_active` (active/paused).
- **Deterministic Matching**:
  - Tag a debit transaction as `expected` (`is_recurring = True`) **only** when merchant keyword, amount tolerance (within `min..max` or ±5% / ₹100), and date window (including weekend drift) **all** match.
  - Ambiguous matches select the highest-scoring commitment and record `match_reason`.
  - Flag mismatches (`amount_high`, `duplicate`, `missed`) with explicit `mismatch_reason`.
  - Expected recurring debits are excluded from "unusual spend" and subscription-leak alerts, and **never** affect the Protect scam message/link checker.
- **Suggestions & Reminders**:
  - Suggest recurring candidates from transaction history (same merchant, similar amount, ~monthly) for explicit user confirmation — never auto-create commitments.
  - Bill reminders (`due_soon` within 7 days, `overdue` past due in IST) are computed deterministically.
- **Security**:
  - Cross-user access returns `404`. Audit all mutations. Apply rate limits.

## Float Health Score (`v1.0.0`)
- **Deterministic, Explainable, Versioned**: `FORMULA_VERSION = "v1.0.0"` in `app/services/health_score_service.py`. Educational indicator only — never gives investment or product recommendations.
- **Components & Weights (total = 100)**:
  - `savings_rate` (**25**): `(income - outflow) / income * 100` (`>=20%` → 100, `10–20%` → 60–100, `0–10%` → 20–60, `<0%` → 0).
  - `emergency_fund_months` (**20**): liquid savings balance / monthly outflow (`>=6m` → 100, `3–6m` → 70–100, `1–3m` → 35–70, `<1m` → 0–35).
  - `debt_to_income` (**20**): monthly EMI commitments / monthly income (`<=15%` → 100, `15–35%` → 60–100, `35–50%` → 25–60, `>50%` → 0).
  - `budget_adherence` (**15**): actual Needs+Wants / planned Needs+Wants (`<=95%` → 100, `95–105%` → 75, `105–120%` → 40, `>120%` → 10).
  - `subscriptions_share` (**10**): monthly recurring subscriptions / monthly income (`<=5%` → 100, `5–10%` → 70, `10–20%` → 35, `>20%` → 10).
  - `insurance_flag` (**10**): user-entered essential insurance flag (`True` → 100, `False` → 25, unset → `insufficient_data`).
- **Missing Data Rule**: Missing or zero-income components return `status = "insufficient_data"` (`score = None`), **never `0`**. Overall score is the weighted average over `available` components only.
- **Bands**: `80–100` (`strong`), `60–79` (`steady`), `40–59` (`building`), `0–39` (`needs_attention`), `None` (`insufficient_data`).
- **Float Path & History**: Ordered next steps across `Protect`, `Plan`, and `Borrow-ready` with `best_next_action` first; snapshots persisted with `formula_version` so deltas are suppressed and flagged (`version_changed=True`) across formula version changes.
