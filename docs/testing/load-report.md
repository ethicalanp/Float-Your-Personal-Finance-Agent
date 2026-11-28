# Local Load & Failure-Injection Report

- **Date**: 2026-11-27
- **Environment**: Local Windows, Python 3.13, in-process ASGI (`httpx.ASGITransport`) against local Docker PostgreSQL (`localhost:5432/float`). No non-local database was touched.
- **Runner**: [load_failure_test.py](file:///d:/PersonalFinanceAgent/scripts/load_failure_test.py)
- **Provider**: `FakeProvider` + `FakeEmbedder` (labeled as fake-provider results; `tracemalloc` peak embedder allocation = **52.84 KB**).

## 1. Scenario Latency, Throughput & SQL Query Counts

| Scenario | Concurrency | Requests | Error Rate | RPS | p50 (ms) | p95 (ms) | p99 (ms) | SQL / req |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `login` | 5 | 25 | 0.0% | 18.33 | 265.33 | 298.14 | 306.75 | 6.0 |
| `upload_csv_20_rows` | 5 | 20 | 0.0% | 13.39 | 335.69 | 508.64 | 512.74 | 66.0 |
| `home_bundle` (`cash-flow`+`budget`+`reminders`) | 8 | 40 | 0.0% | 25.85 | 303.58 | 376.02 | 386.92 | 15.0 |
| `chat_fake_provider` | 5 | 25 | 0.0% | 51.97 | 91.54 | 101.33 | 103.29 | 6.0 |
| `chat_slow_provider_400ms` | 5 | 15 | 0.0% | 54.39 | 87.33 | 104.23 | 104.23 | 6.0 |
| `mixed_users` | 6 | 30 | 0.0% | 25.77 | 134.80 | 471.80 | 562.61 | 17.0 |
| `failure_slow_db_150ms` (`home_bundle`) | 5 | 15 | 0.0% | 7.75 | 633.19 | 705.74 | 705.74 | 15.0 |

*(Note: `chat_slow_provider_400ms` stayed ~87ms because the test adapter overrode `generate()` rather than `complete()`, so `LLMGateway` used the fast `FakeProvider.complete()` path.)*

## 2. Failure Injection Results

| Injection | Before Fix | After Fix | Behavior |
|---|---:|---:|---|
| **DB down (`/ready`)** | `200` | `503` | `/ready` now executes `SELECT 1` and returns `503` (`database: unavailable`) when DB fails. |
| **DB down (`GET /api/v1/plan/cash-flow`)** | `500` (unhandled `OperationalError`) | `503` | `main.py` catches `OperationalError` and returns structured `DATABASE_UNAVAILABLE` `503`. |
| **LLM `429` (`RateLimited`)** | `200` | `200` | Chat degrades gracefully to deterministic fallback without `500`. |
| **Slow DB (`+150ms` per session yield)** | `200` (0% err) | `200` (0% err) | `home_bundle` p50 rose from `303.58 ms` to `633.19 ms` (`7.75 RPS`). |

## 3. Bottleneck & Index Findings (with Evidence)

1. **N+1 Queries on CSV Upload (`66.0` SQL queries/req for 20 rows)**:
   - Evidence: `upload_csv_20_rows` executed `1,320` SQL statements across `20` requests (`66.0` queries/request, `p95 = 508.64 ms`). Each parsed row issues per-row `dedupe_hash` / recurring matching queries instead of a batched `IN (...)` lookup and bulk insert.
2. **Missing DB Readiness & Outage Handling (Fixed in this branch)**:
   - Evidence: Baseline `db_down` injection returned `200` on `/ready` and `500` on `/api/v1/plan/cash-flow`. Fixed in [health.py](file:///d:/PersonalFinanceAgent/apps/api/app/api/v1/health.py) and [main.py](file:///d:/PersonalFinanceAgent/apps/api/app/main.py), verified by [test_db_failure_503.py](file:///d:/PersonalFinanceAgent/apps/api/tests/test_db_failure_503.py).
3. **Home Bundle Query Fan-Out (`15.0` SQL queries/req)**:
   - Evidence: Fetching `cash-flow`, `budget`, and `reminders` sequentially runs `15` queries (`3` auth/consent lookups + `12` domain queries).

## 4. Real Embedder (`intfloat/multilingual-e5-base`) Load & Memory Benchmark
- **Test**: `pytest -s -m real_embedder tests/ai/test_real_embedder_load.py` (CPU, local HuggingFace cache).
- **Cold Load + First Query**: `49,581.0 ms` (~49.6s, includes `torch`/`sentence-transformers` import + model load).
- **Warm Query Latency**: `p50 = 178.3 ms`, `p95 = 302.9 ms` (`n = 5` EN/ML/Manglish queries).
- **Batch-16 Passage Embedding**: `664.9 ms` (`41.6 ms/passage`).
- **Peak Traced Memory (`tracemalloc`)**: `1,409.12 MB` (~1.41 GB).
- **Note on CSV Upload N+1**: Fixed in `apps/api/app/api/v1/plan.py` + `apps/api/app/services/recurring_service.py` (`match_transactions_bulk`), verified by constant-query-count regression test `test_upload_statement_avoids_n_plus_1_queries`.
