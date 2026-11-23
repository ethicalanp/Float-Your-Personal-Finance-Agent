# Provider Portability & Switching Runbook

This runbook documents how to switch the active LLM provider in Float's AI Subsystem without modifying any application code. Provider selection, model configuration, and safety approval flags are driven entirely by environment variables.

---

## 1. Provider Architecture & Portability Overview

The Float AI Gateway (`app.ai.gateway`) uses an adapter abstraction (`BaseAdapter`) that decouples application logic (routing, tool orchestration, RAG answers, and fact grounding) from specific model vendors.

```
┌────────────────────────────────────────────────────────┐
│             Float Application Orchestrator             │
│            (app.ai.agent.orchestrator)                 │
└──────────────────────────┬─────────────────────────────┘
                           │ Typed LLMRequest
                           ▼
┌────────────────────────────────────────────────────────┐
│                 LLM Gateway Manager                    │
│                 (app.ai.gateway.manager)               │
│  - Privacy / Masking Enforcement                       │
│  - Circuit Breaker & Retry with Jitter                 │
│  - Cost & User Daily Token Quotas                      │
│  - Structured Output Repair Prompting                  │
└──────────────┬──────────────────────────┬──────────────┘
               │ Primary                  │ Fallback (Automatic)
               ▼                          ▼
      ┌─────────────────┐        ┌─────────────────┐
      │ Primary Adapter │        │ Fallback Adapter│
      │ (e.g. Groq)     │        │ (e.g. Gemini)   │
      └─────────────────┘        └─────────────────┘
```

---

## 2. Supported Providers & Configuration Matrix

Every provider configuration uses the `PFA_LLM_` environment variable prefix.

| Environment Variable | Description | Example Values |
| :--- | :--- | :--- |
| `PFA_LLM_PROVIDER` | Primary adapter name | `fake`, `openai_compatible`, `gemini`, `anthropic` |
| `PFA_LLM_MODEL` | Target model name | `llama-3.3-70b-versatile`, `gemini-1.5-flash`, `claude-3-5-sonnet-20241022` |
| `PFA_LLM_API_KEY` | Provider API key (SecretStr, masked in logs) | `gsk_...`, `AIza...`, `sk-ant-...` |
| `PFA_LLM_BASE_URL` | API endpoint URL (for OpenAI-compatible providers) | `https://api.groq.com/openai/v1`, `https://openrouter.ai/api/v1` |
| `PFA_LLM_TIMEOUT_SECONDS` | Per-request timeout in seconds | `15.0` (default) |
| `PFA_LLM_APPROVED_FOR_REAL_DATA` | Privacy flag (`true` allows masked real user data) | `false` (default), `true` |

---

## 3. Provider Switching Step-by-Step

### Scenario A: Local Development & CI (`fake`)
For automated CI pipelines, fast unit tests, and disconnected local environments:
```bash
export PFA_LLM_PROVIDER="fake"
export PFA_LLM_MODEL="fake-eval-v1"
export PFA_LLM_APPROVED_FOR_REAL_DATA="true"
```

### Scenario B: Groq (OpenAI-Compatible Llama 3.3 70B)
For ultra-fast, low-latency grounded reasoning:
```bash
export PFA_LLM_PROVIDER="openai_compatible"
export PFA_LLM_BASE_URL="https://api.groq.com/openai/v1"
export PFA_LLM_API_KEY="gsk_your_groq_api_key_here"
export PFA_LLM_MODEL="llama-3.3-70b-versatile"
export PFA_LLM_APPROVED_FOR_REAL_DATA="true"
```

### Scenario C: Google Gemini 1.5 Flash / Pro
For complex reasoning or high token-window contexts:
```bash
export PFA_LLM_PROVIDER="gemini"
export PFA_LLM_API_KEY="AIzaSy_your_gemini_api_key"
export PFA_LLM_MODEL="gemini-1.5-flash"
export PFA_LLM_APPROVED_FOR_REAL_DATA="true"
```

### Scenario D: Anthropic Claude 3.5 Sonnet
```bash
export PFA_LLM_PROVIDER="anthropic"
export PFA_LLM_API_KEY="sk-ant-api03-your_anthropic_api_key"
export PFA_LLM_MODEL="claude-3-5-sonnet-20241022"
export PFA_LLM_APPROVED_FOR_REAL_DATA="true"
```

---

## 4. Fallback Provider Configuration (Automatic Failover)

To protect uptime during upstream vendor outages or HTTP 429 rate limits, configure a secondary fallback provider. If the primary provider fails after bounded retries, the gateway transparently routes the request to the fallback provider.

```bash
# Primary: Groq
export PFA_LLM_PROVIDER="openai_compatible"
export PFA_LLM_BASE_URL="https://api.groq.com/openai/v1"
export PFA_LLM_API_KEY="gsk_..."
export PFA_LLM_MODEL="llama-3.3-70b-versatile"

# Automatic Fallback: Gemini
export PFA_LLM_FALLBACK__PROVIDER="gemini"
export PFA_LLM_FALLBACK__MODEL="gemini-1.5-flash"
export PFA_LLM_FALLBACK__API_KEY="AIzaSy..."
export PFA_LLM_FALLBACK__APPROVED_FOR_REAL_DATA="true"
```

---

## 5. Verification Runbook

After switching environment variables and restarting the service, execute these verification steps:

### 1. Verify Subsystem Health Endpoint
```bash
curl -X GET http://localhost:8000/api/v1/assistant/health \
  -H "Accept: application/json"
```
**Expected Response:**
```json
{
  "status": "healthy",
  "database": { "status": "ok", "latency_ms": 1.2 },
  "embedder": { "status": "ok", "details": { "model_name": "intfloat/multilingual-e5-base", "dimension": 768 } },
  "gateway": {
    "status": "ok",
    "details": {
      "provider": "openai_compatible",
      "model": "llama-3.3-70b-versatile",
      "circuit_state": "closed",
      "approved_for_real_data": true
    }
  }
}
```

### 2. Verify Metrics Exposition
```bash
curl -X GET http://localhost:8000/api/v1/assistant/metrics
```
Verify that `pfa_assistant_requests_total` and stage latency summaries are available.

### 3. Run Deterministic Evaluation Suite
```bash
python -m app.ai.evals.run --suite tools,security --provider configured
```
Ensure 0 security violations and 100% financial arithmetic correctness.
