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
