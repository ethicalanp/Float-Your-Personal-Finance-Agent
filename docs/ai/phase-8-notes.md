# Phase 8 Engineering Notes: Production Hardening, Observability, and Retention (Honesty Pass)

## 1. What Was Built & Hardened

1. **Observability & Prometheus Metrics (`app/ai/observability/metrics.py` & `/assistant/metrics`)**:
   - Thread-safe `AssistantMetricsRegistry` exporting Prometheus text format (v0.0.4).
   - Metrics:
     - `pfa_assistant_requests_total{route, status, lang}`: Counter tracking requests by intent, outcome, and language.
     - `pfa_assistant_stage_latency_seconds{stage, quantile}`: Summary recording latency across `route`, `tools`, `retrieval`, and `compose` stages with P50/P95 quantiles.
     - `pfa_assistant_fallbacks_total{reason}`: Counter tracking graceful degradation and fallback invocations.
   - **Auth Lockdown**: Access to `GET /api/v1/assistant/metrics` is locked down. Requires either:
     - `X-Internal-Token: <INTERNAL_METRICS_TOKEN>` header (configured via `internal_metrics_token` in `app/core/config.py`), or
     - Authenticated Bearer JWT token.
     - Unauthenticated requests receive HTTP 401 Unauthorized.
   - **Multi-Worker In-Memory Limitation**: Note that metrics counters are stored in-memory per worker process. In multi-process production deployments (e.g. multi-worker Uvicorn/Gunicorn), an external aggregator (such as Prometheus Pushgateway, Redis counters, or StatsD) must be used.

2. **Dedicated AI Subsystem Health Endpoints**:
   - **Minimal Liveness Probe (`GET /api/v1/assistant/health`)**:
     - Reduced to an unauthenticated, zero-leak liveness response: `{"status": "healthy", "service": "assistant", "timestamp": "..."}`.
     - Safe for public load balancers and orchestrator liveness checks; exposes no internal topology, latencies, or model identifiers.
   - **Authenticated Diagnostic Probe (`GET /api/v1/assistant/health/details`)**:
     - Requires authenticated Bearer token.
     - Reports component details:
       - `database`: Runs `SELECT 1` and reports query latency.
       - `embedder`: Reports active embedder model (`intfloat/multilingual-e5-base` or `FakeEmbedder`) and vector dimension.
       - `gateway`: Reports provider name, target model, circuit breaker state (`closed`, `half_open`, `open`), and real-data approval status.

3. **User-Facing Right-to-Erasure Endpoint (`DELETE /api/v1/assistant/conversations`)**:
   - Removed "GDPR/DPDP-compliant" phrasing; defined via concrete technical data retention semantics.
   - **Confirmation Guard**: Requires confirmation payload:
     `{"confirm": true, "confirmation_phrase": "DELETE_MY_CONVERSATIONS"}`. Returns HTTP 400 if confirmation phrase is absent or incorrect.
   - **Hard Delete Scope**: Atomically executes permanent SQL `DELETE` on:
     - `Message` records linked to the user's conversations.
     - `Conversation` records belonging to the authenticated user.
     - `AuditTrail` records where `user_id == current_user.id` and `action == "assistant_chat"`.
   - **Clarification on `/knowledge` turns**: Ephemeral knowledge questions do not create conversation rows, but generate `AuditTrail` rows with action `assistant_chat`. Purging audit rows for `assistant_chat` removes all traces of knowledge questions.
   - **Cross-User Isolation**: Tested via `test_purge_conversations_user_isolation`, proving User A cannot delete User B's data.
   - **Audit Anonymization Proposal**: In production banking contexts, future work should support an anonymization mode that unlinks user identity and strips query content while preserving operational telemetry for auditing:
     `UPDATE audit_trail SET user_id = '00000000-0000-0000-0000-000000000000', client_ip = '0.0.0.0', metadata = metadata - 'query' - 'answer' WHERE user_id = :user_id AND action = 'assistant_chat'`.

4. **Production Request Hardening & Size Caps**:
   - `AssistantChatRequest`: Enforces `min_length=1`, `max_length=2000` on input query text.
   - `KnowledgeQuestionRequest`: Enforces `min_length=3`, `max_length=1000` on regulatory query text.
   - Database read-only transaction mode (`SET TRANSACTION READ ONLY`) and statement timeouts enforced during tool executions.

5. **Provider Portability Runbook (`docs/ai/provider-switch-runbook.md`)**:
   - Operational runbook demonstrating zero-code provider switching across Fake, Groq (OpenAI-compatible), Google Gemini, and Anthropic Claude via `PFA_LLM_` environment variables.
   - Upstream Groq probe report: Local `.env` contains `GROQ_API_KEY`, but upstream returned HTTP 401 AuthError (expired/unauthorized). Live evaluations remain a manual operational step when valid credentials are supplied.

---

## 2. Test Verification Results

All 144 AI subsystem unit, integration, and security tests pass deterministically:
```
tests/ai/test_agent_orchestrator.py .................. [16 passed]
tests/ai/test_assistant_api.py ...................... [ 6 passed]
tests/ai/test_assistant_status_api.py ............... [ 2 passed]
tests/ai/test_eval_framework.py ..................... [ 5 passed]
tests/ai/test_financial_tools.py .................... [18 passed]
tests/ai/test_gateway_adapters.py .................. [ 2 passed]
tests/ai/test_gateway_config_and_keys.py ............ [ 3 passed]
tests/ai/test_gateway_resilience.py ................. [ 7 passed]
tests/ai/test_rag_answer.py ......................... [11 passed]
tests/ai/test_rag_pipeline.py ....................... [47 passed]
tests/ai/test_rag_url_safety.py ..................... [11 passed]
tests/ai/test_security_masking.py .................. [10 passed]
tests/ai/test_security_untrusted.py ................. [ 5 passed]
======================= 144 passed in 6.13s =======================
```

Total project test suite: **210 passed, 0 failed** in 11.20s.

Code quality and types:
- `ruff check app tests`: **All checks passed!**
- `mypy app --ignore-missing-imports`: **Success: no issues found in 123 source files.**

---

## 3. Decisions Confirmed
1. **Metrics Auth Token**: Added `internal_metrics_token` to `app/core/config.py` with fallback to authenticated Bearer token.
2. **Health Probe Segregation**: Minimal liveness probe (`/health`) avoids leaking infrastructure details to unauthenticated callers; diagnostic details (`/health/details`) require authentication.
3. **Explicit Purge Confirmation**: Requiring `confirmation_phrase="DELETE_MY_CONVERSATIONS"` guards against accidental UI clicks or automated client bugs.

---

## 4. Not Done / Known Gaps (Phase 8 Items)

The following items from the Phase 8 specification are not implemented in the current repository:
1. **Load Testing**: Distributed benchmark tests under high concurrent load (Locust / k6) have not been run.
2. **Failure Injection / Chaos Testing**: Automated chaos injection for mid-pipeline database disconnects or network packet loss is not implemented.
3. **Multi-Provider Live Portability Proof**: Live side-by-side execution across two active commercial providers simultaneously has not been completed.
4. **Native Gemini/Anthropic Adapter SDK Unit Tests**: Dedicated unit test suites exercising the official Google GenAI or Anthropic Python SDKs with live/recorded HTTP cassettes are not yet implemented.
5. **Semantic Query Caching**: In-memory or Redis-based semantic vector query caching is not built.
6. **MLflow Prompt Registry**: Integration with MLflow or LangSmith for prompt lifecycle tracking is not integrated.
7. **CI Dependency & Container Scanning**: CI workflows do not yet include automated container vulnerability scans (Trivy) or dependency auditing (`pip-audit`).
8. **Graceful Shutdown Signal Handling**: In-flight LLM call draining on OS `SIGTERM` / `SIGINT` signals is not implemented.
9. **Kubernetes Readiness vs Liveness Probe**: Formal separate `/ready` endpoint checking database pool warm-up and embedder memory loading is not yet split from `/health`.

---

## 5. Verification Commands
```powershell
# Run full AI test suite
cd apps/api
..\..\venv\Scripts\pytest.exe tests/ai/ -v

# Run linting and static typing
..\..\venv\Scripts\ruff.exe check app tests
..\..\venv\Scripts\mypy.exe app --ignore-missing-imports

# Verify metrics endpoint requires auth
curl -X GET http://localhost:8000/api/v1/assistant/metrics
```
