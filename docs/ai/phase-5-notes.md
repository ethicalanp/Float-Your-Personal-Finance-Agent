# Phase 5 Implementation Notes: Permissioned, Typed, Read-Only Financial Tools

## 1. Overview and Core Invariants

Phase 5 introduces Float's financial analytical tool subsystem located in `apps/api/app/ai/tools/`.
These tools allow an AI assistant to analyze authenticated user data while strictly enforcing:
1. **The LLM never gets database access, SQL, or ML model internals.** It can only invoke registered, typed, read-only tools.
2. **Context Isolation**: User identity (`user_id`) comes strictly from the authenticated request context (`ToolContext`). Tool input models reject `extra="forbid"`, and exported LLM schemas never contain `user_id`, `account_id`, or free-form query strings.
3. **Database Read-Only Enforcement**: Enforced at the engine and statement execution level (PostgreSQL `SET TRANSACTION READ ONLY` + statement timeout, intercepting write statements and ORM modifications).
4. **Deterministic Arithmetic & Grounded Facts**: All monetary numbers use `Decimal` formatted to 2 places (`ROUND_HALF_UP`). Tools produce atomic `Fact` objects (`id`, `label`, `value`, `unit`, `period`) which Phase 6 will use to verify that every number in an answer matches a validated tool fact.
5. **No Invented Credit Scores**: `get_borrow_readiness` returns indicative bands (`low`, `fair`, `good`, `strong`) or `insufficient_data`. It never exposes internal ML default probabilities or invents a numerical credit score.

---

## 2. Package Architecture

```
apps/api/app/ai/tools/
├── __init__.py           # Package exports and tool auto-registration
├── base.py               # ToolContext, Fact, ToolResult, Tool dataclass, Decimal rounding helpers
├── errors.py             # ToolError and safe ToolErrorCode taxonomy
├── registry.py           # ToolRegistry, schema security auditor, and default_registry
├── executor.py           # ToolExecutor, ToolExecutionBudget, and enforce_read_only_session
└── financial_tools.py    # 6 core financial analytical tools and registration handler
```

---

## 3. Financial Analytical Tools

| Tool Name | Input Arguments | Output Metrics & Facts | Grounding Rules |
| :--- | :--- | :--- | :--- |
| `get_spending_summary` | `start_date`, `end_date` | `total_spent`, `total_income`, `net_cash_flow`, `transaction_count`, `unclassified_percentage` | Excludes internal `Transfers`; debits = spending, credits = income. Warns if uncategorized > 20%. |
| `get_category_breakdown` | `start_date`, `end_date`, `top_n` (1-20) | Top categories with `total_amount`, `percentage_of_total`, plus aggregated `other_amount` | Sorted descending; percentage share computed deterministically with half-up rounding. |
| `compare_periods` | `period_a_start`, `period_a_end`, `period_b_start`, `period_b_end` | Differences (`spending_difference`, `income_difference`, `net_difference`) and percentage changes | Warns if period durations differ. Safe zero-baseline percentage change handling (no division by zero). |
| `get_cash_flow` | `start_date`, `end_date`, `granularity` (`daily`/`weekly`/`monthly`) | Aggregated buckets with `inflow`, `outflow`, `net`, `average_net_per_period`, and extrema | Chronological bucketing for trend analysis. |
| `list_recurring_payments` | `is_active` (bool) | Active commitments, normalized `monthly_equivalent`, and `total_monthly_committed` | Normalizes quarterly (/3) and yearly (/12) cadence to monthly commitments. |
| `get_borrow_readiness` | `refresh` (bool) | `status` (`available` or `insufficient_data`), `readiness_band`, `top_factors`, recommendations | **Never invents a score**. If no assessment exists, returns `insufficient_data`. |

---

## 4. Security Verification

### A) Schema Isolation Audit
`registry.assert_schema_is_secure(schema)` inspects all properties and descriptions of exported tool function declarations.
If any prohibited field name (`user_id`, `account_id`, `owner_id`, `sql`, `raw_sql`, `query_string`) is present, it throws `SchemaSecurityViolationError`.

### B) Read-Only Database Mode
Inside `enforce_read_only_session`:
- PostgreSQL: Executes `SET TRANSACTION READ ONLY;` and `SET statement_timeout = '5000ms';`.
- Query Interception: Blocks any statement starting with `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, or `TRUNCATE`, raising `ToolError("forbidden", ...)`.
- ORM Interception: Rejects any flush when `session.new`, `session.dirty`, or `session.deleted` contains objects.

### C) Resource Limits & Budgeting
`ToolExecutionBudget` enforces:
- Max tool calls per user turn (default 5).
- Max total result rows (default 500), automatically flagging `truncated=True` if exceeded.
- Overall wall-clock budget (default 10.0s), aborting with `ToolError("timeout", ...)` if exceeded.

---

## 5. Test Suite Verification

Comprehensive test suite in `tests/ai/test_financial_tools.py`:
- `test_registered_tool_schemas_contain_no_prohibited_fields`: Validates that all exported tool schemas are free of identity and query fields.
- `test_schema_security_violation_rejection`: Asserts that any schema introducing `user_id` is rejected.
- `test_quantize_currency_and_percent`: Tests half-up rounding at 2 decimal places.
- `test_calculate_percentage_change_zero_baseline`: Verifies zero-baseline safely returns `None` and an explanatory warning.
- `test_calculate_percentage_change_valid`: Tests positive and negative percentage changes.
- `test_read_only_enforcement_blocks_sql_writes`: Confirms direct SQL write attempts fail with `forbidden`.
- `test_read_only_enforcement_blocks_orm_flush`: Confirms ORM flushes fail with `forbidden`.
- `test_executor_blocks_unauthorized_write_tool`: Confirms tools attempting database mutations are blocked by the executor.
- `test_get_spending_summary`: Tests spending/income calculations and exclusion of transfers.
- `test_get_category_breakdown`: Tests top-N category ranking, other bucket aggregation, and percentage shares.
- `test_compare_periods`: Tests period diffs, percentage changes, and duration mismatch warnings.
- `test_get_cash_flow`: Tests cash flow bucketing and average net computation.
- `test_list_recurring_payments`: Tests frequency normalization and monthly commitment totals.
- `test_get_borrow_readiness_no_score_invented`: Tests missing assessment handling and verified indicative band retrieval without score invention.
- `test_executor_rejects_extra_arguments`: Tests Pydantic `extra="forbid"` rejection of unauthorized parameters.
- `test_executor_rejects_unknown_tool`: Tests structured 404/not_found error for unknown tools.
- `test_executor_enforces_budget_limits`: Tests request-level max tool calls enforcement.

**Status**: 17/17 Phase 5 tool tests passed. Full test suite: **194 passed in 8.57s**. Static typing (`mypy app`): 0 issues across 105 files. Linter (`ruff check app tests`): 0 issues.
