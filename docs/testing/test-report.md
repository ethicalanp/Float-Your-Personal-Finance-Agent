# Test Audit & MVP Verification Report

## 1. Scope & Execution
- **Environment**: Python 3.13 / PostgreSQL 17 + pgvector (`float-postgres` container)
- **Suite**: Full test suite across auth, plan, protect, borrow, assistant, admin, and AI evaluation modules.
- **Verification Command**: `scripts\ci_local.cmd` (runs ruff, mypy, alembic upgrade, alembic check, pytest on a throwaway database).

## 2. Test Coverage Summary per Module
`python -m pytest --cov=app --cov-report=term-missing -q`
- **Total Suite Coverage**: 73% (9607 statements, 2585 missed, 302 tests passing)

| Module | Coverage | Key Component Coverage |
|---|---|---|
| `auth` / `consent` | ~80% | `security.py` (92%), `user.py` (79%), `auth.py` (63%) |
| `plan` / `import` | ~79% | `models/plan.py` (99%), `statement_parser.py` (92%), `categorizer.py` (91%), `cash_flow.py` (80%), `api/v1/plan.py` (54%) |
| `protect` | ~83% | `models/protect.py` (99%), `scam_classifier.py` (95%), `verified_contacts.py` (93%), `scam_detector.py` (91%), `api/v1/protect.py` (65%) |
| `borrow` | ~66% | `models/borrow.py` (100%), `borrow_recommender.py` (88%), `borrow_model.py` (79%), `api/v1/borrow.py` (72%), `borrow_features.py` (39%) |
| `assistant` | ~70% | `conversations.py` (100%), `router.py` (82%), `planner.py` (81%), `composer.py` (79%), `api/v1/assistant.py` (67%), `orchestrator.py` (60%) |
| `admin` | ~77% | `models/admin.py` (100%), `panel.py` (95%), `auth.py` (94%), `views.py` (78%), `create_admin.py` (38%) |
| `ai/*` (core RAG/Tools) | ~82% | `untrusted.py` (100%), `base.py` (98%), `financial_tools.py` (97%), `masking.py` (94%), `answer.py` (89%), `policy_guard.py` (88%), `retrieval.py` (78%) |
| `ai/evals` (offline) | ~27% | `datagen.py` (36%), `report_html.py` (30%), `experiment.py` (14%) |

### 10 Least-Covered Files & Proposed Targets
1. `app/ai/evals/experiment.py`: 14% -> Target: 50% (offline CLI evaluation script)
2. `app/ai/evals/report_html.py`: 30% -> Target: 60% (offline HTML visualizer)
3. `app/ai/evals/datagen.py`: 36% -> Target: 60% (synthetic generation CLI)
4. `app/admin/create_admin.py`: 38% -> Target: 70% (terminal admin creation script)
5. `app/services/borrow_features.py`: 39% -> Target: 75% (untested aggregate feature calculation branches)
6. `app/api/v1/plan.py`: 54% -> Target: 80% (manual transaction modification routes)
7. `app/ai/agent/orchestrator.py`: 60% -> Target: 80% (multi-turn orchestrator fallbacks and tool retry loops)
8. `app/services/recurring_service.py`: 60% -> Target: 75% (interval matching and pattern heuristics)
9. `app/core/dependencies.py`: 63% -> Target: 85% (token extraction and consent rejection branches)
10. `app/api/v1/auth.py`: 63% -> Target: 80% (token refresh and password reset edge cases)

## 3. Bugs Discovered & Fixed
1. **Uncaught Base64/JSON Token Decode Exceptions** (`app/core/security.py`):
   - *Issue*: Malformed `Bearer` tokens triggered `binascii.Error`, `ValueError`, `json.JSONDecodeError`, or `UnicodeDecodeError`, resulting in unhandled HTTP 500 errors instead of 401.
   - *Fix*: Wrapped token decoding in `try-except (binascii.Error, ValueError, json.JSONDecodeError, UnicodeDecodeError)` and raised `UnauthorizedException("Invalid token format") from None`.
2. **Missing Model 500 Internal Error** (`app/services/borrow_model.py`):
   - *Issue*: When XGBoost model artifact was missing, borrow endpoint raised unhandled `FileNotFoundError` (500).
   - *Fix*: Caught `FileNotFoundError` and raised `ServiceUnavailableException` (503) preserving service degradation contract.
3. **Floating Point Precision Drift in Cash Flow** (`app/services/cash_flow.py`):
   - *Issue*: Float accumulation caused IEEE-754 precision issues in financial balances.
   - *Fix*: Standardized cash-flow calculations on exact `Decimal` arithmetic.
4. **Statement Parser BOM & Decimal Errors** (`app/services/statement_parser.py`):
   - *Issue*: UTF-8 BOM byte sequence corrupted column headers; malformed decimal strings caused 500s.
   - *Fix*: Stripped BOM (`utf-8-sig`) and safely validated decimal tokens.
5. **Unbounded Statement Upload Memory Buffering** (`app/core/middleware.py`, `app/api/v1/plan.py`):
   - *Issue*: FastAPI buffered full statement payloads into RAM before endpoint validation, vulnerable to memory exhaustion on oversized uploads.
   - *Fix*: Created `StatementUploadLimitMiddleware` enforcing two-tier protection: early rejection on `Content-Length > 10 MB` and a capped streaming read `capped_receive()` aborting immediately if cumulative stream bytes exceed 10 MB.
6. **Slow Test Execution / Hang in Serialization** (`tests/test_plan_edge_cases.py`):
   - *Issue*: 350k lines generated in test payload hung `TestClient` JSON serialization (>30s timeout).
   - *Fix*: Refactored to single-line ASCII string buffer (<1ms execution).
7. **Duplicate Admin Model Table Registration** (`tests/test_admin.py`):
   - *Issue*: Duplicate table entries in `APP_TABLES` caused `sqlite3.OperationalError: table knowledge_documents already exists`.
   - *Fix*: Deduplicated table registrations prior to creating SQLite in-memory schema.

## 4. End-to-End MVP Flow (`test_mvp_end_to_end_flow`)
The end-to-end suite exercises all 11 core user journey steps on real PostgreSQL + pgvector:
1. **Register**: User creation, DPDP consent capture, JWT issuance (`/api/v1/auth/register`).
2. **Login**: Credential authentication and token acquisition (`/api/v1/auth/login`).
3. **Consent**: Active terms and AI processing consent validation (`/api/v1/auth/consent`).
4. **Account & Statement Upload**: Account creation and CSV statement parsing with deduplication (`/api/v1/plan/upload-statement`).
5. **Cash Flow**: Income/expense aggregation and net savings calculation (`/api/v1/plan/cash-flow`).
6. **Scam Check**: Multilingual scam detection with 1930 guidance (`/api/v1/protect/check`).
7. **Recovery Case**: Incident tracking and dynamic checklist generation (`/api/v1/protect/recovery-cases`).
8. **Borrow**: Credit readiness assessment with indicative legal disclaimer and graceful 503 degradation (`/api/v1/borrow/assess`).
9. **Knowledge Question with Citations**: Grounded regulatory Q&A with pgvector retrieval and citation verification (`/api/v1/assistant/knowledge`).
10. **Chat Orchestration**: Multi-turn chat assistant coordinating tools and financial contexts (`/api/v1/assistant/chat`).
11. **Conversation Purge**: Complete DPDP-compliant conversation history erasure (`DELETE /api/v1/assistant/conversations`).
