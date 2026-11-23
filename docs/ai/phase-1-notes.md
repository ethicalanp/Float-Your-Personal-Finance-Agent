# Phase 1: LLM Gateway & Security Foundation Notes

## Overview
Phase 1 establishes the production-grade LLM Gateway and Security foundation for the Float platform in `apps/api/app/ai/`. It provides a privacy-preserving, resilient, multi-provider abstraction that strictly adheres to the hard safety rules established in the Phase 0 Architecture Specification.

## Subsystem Architecture

### 1. Security & Privacy Package (`app/ai/security/`)
- **PII Masking (`masking.py`)**:
  - Regex and Luhn validation covering Indian financial identifiers:
    - Mobile numbers (`+91-XXXXX-X1234`)
    - UPI IDs (`u***r@okhdfcbank`, `s***p@upi`)
    - Email addresses (`j***n@example.com`)
    - Permanent Account Number / PAN (`XXXXX1234X`)
    - Aadhaar (`XXXX-XXXX-1234`)
    - Credit/Debit cards (`****-****-****-1234` only for Luhn-valid sequences)
    - Bank account numbers in context / IFSC adjacent (`****1234`)
    - OTP / PIN stated in English, Malayalam, or Manglish (`[MASKED_OTP]`)
    - Known full names (`[PERSON_NAME]`)
  - **Strict Preservation**: Currency figures (e.g. `₹2,500.00`, `Rs. 18,400`, `INR 450`, `18400`) and dates (`2026-11-21`, `21/11/2026`) are **NEVER** masked.
- **Fail-Closed Leak Scanner (`leak_scanner.py`)**:
  - Scans post-mask text for unmasked high-risk PII patterns.
  - If any unmasked credit card, 12-digit Aadhaar, clean PAN, or raw phone is found, raises `MaskingFailed` to abort execution before any external call.
- **Untrusted Data Wrapper (`untrusted.py`)**:
  - Encloses third-party documents, SMS, and user inputs into delimited `<data source="..." name="...">...</data>` blocks.
  - Strips non-printable ASCII control characters.
  - Neutralizes tag-breakout attempts (e.g. `</data>` replaced with `&lt;/data&gt;`).
  - Prepends a standing security instruction commanding the model to treat content strictly as untrusted literal text, never as commands or instructions.
- **Safe Tracing (`tracing.py`)**:
  - Emits telemetry for latency, prompt version, provider, model, token usage, and error types.
  - Strictly guarantees that raw prompts, user texts, LLM answers, or financial numbers are never recorded in logs.

### 2. LLM Gateway Package (`app/ai/gateway/`)
- **Configuration (`config.py`)**:
  - Pydantic Settings reading `PFA_LLM_*` environment variables.
  - Uses `SecretStr` for `api_key` with overridden `__repr__` and `__str__` to guarantee keys never leak into logs or exception traces.
  - Supports automatic fallback to `GROQ_API_KEY` when provider is `groq`.
  - In production mode (`APP_ENV=production`), logs a warning if `approved_for_real_data=False` and rejects real customer requests with `ProviderNotApproved`.
- **Interface & Types (`types.py`, `errors.py`)**:
  - `LLMRequest` contains messages, prompt version, trace ID, `user_id` (used strictly for token budget enforcement, never sent upstream to providers), and `data_class` (`demo` vs `masked_real`).
  - Clear error taxonomy: `RateLimited(retry_after)`, `TransientProviderError`, `Timeout`, `AuthError`, `BadRequest`, `InvalidStructuredOutput`, `BudgetExceeded`, `CircuitOpen`, `ProviderNotApproved`, `MaskingFailed`.
  - `to_user_safe_message` function maps errors to safe user-facing feedback without exposing system internals.
- **Adapters (`adapters/`)**:
  - `OpenAICompatibleAdapter`: Shared async HTTP client with connection pooling, configurable base URL, and capabilities-aware payload formatting (Groq, OpenAI, Azure, vLLM).
  - `FakeProvider`: Deterministic, scriptable provider with FIFO response/exception queue for tests.
  - Clear extension stubs for Anthropic and Google Gemini.
- **Resilience Engine (`resilience.py`)**:
  - Bounded exponential backoff with full jitter.
  - Respects HTTP 429 `Retry-After` headers.
  - Only retries 429, 5xx, and timeouts; non-transient errors fail fast.
  - 3-state Circuit Breaker (`CLOSED`, `OPEN`, `HALF_OPEN`) preventing cascading provider failures.
  - Concurrency control with `asyncio.Semaphore` and a 5-second queue timeout.
- **Structured Output Repair (`manager.py`)**:
  - Validates model responses against Pydantic models or JSON schemas.
  - If output fails schema validation, performs **exactly one repair attempt** with a targeted repair prompt.
  - If repair fails, raises `InvalidStructuredOutput`.
- **Budgets & Cache (`budgets.py`, `cache.py`, `context_window.py`)**:
  - Request token budget and daily per-user token budget store (`InMemoryBudgetStore`).
  - Deterministic TTL response cache for zero-temperature requests.
  - Conservative context window pruner retaining system instructions and the last 6 conversational turns within 2,000 estimated tokens (with Malayalam token explosion safety).

### 3. Assistant Status Endpoint (`app/api/v1/assistant.py`)
- `GET /api/v1/assistant/status`:
  - Authenticated endpoint reporting AI subsystem status (`available`, `degraded`, `unavailable`), provider, model, circuit breaker state, and real-data approval status.
  - Exposes zero keys or secret tokens.
  - System health checks (`/health`) remain completely decoupled from LLM availability.

## Running Tests & Smoke Verification

### Run Automated Tests
```powershell
Set-Location apps/api
pytest tests/ai/ -v
```

### Run Full Test Suite (Existing + AI)
```powershell
Set-Location apps/api
pytest -v
```

### Run Static Analysis
```powershell
ruff check apps/api
Set-Location apps/api; mypy app
```

### Run Manual Smoke Script
```powershell
Set-Location apps/api
python scripts/llm_smoke.py
```
*(If `GROQ_API_KEY` is present in `.env`, it will query Groq Llama 3.3 70B live; otherwise it uses the deterministic FakeProvider.)*
