# Phase 6 Implementation Notes: Intent Router and Orchestration

## 1. Overview and Core Invariants

Phase 6 implements Float's primary conversational agent orchestration engine in `apps/api/app/ai/agent/`.
The orchestrator coordinates the end-to-end user query lifecycle across Float's permissioned tools, hybrid RAG retriever, and LLM gateway.

### Core Architectural Invariants
1. **Explicit, Deterministic State Machine**: Every request advances through explicit states (`RECEIVED` -> `CONSENT_CHECK` -> `MASK` -> `ROUTE` -> `PLAN` -> `EXECUTE_TOOLS`/`RETRIEVE` -> `VALIDATE_EVIDENCE` -> `COMPOSE` -> `VALIDATE_ANSWER` -> `RESPOND`). There are no autonomous LLM tool-calling loops.
2. **Zero-Tolerance Safety Override for Fraud**: Any query containing fraud, scam, OTP, unauthorized transactions, or cybercrime indicators is unconditionally routed to `protect` via regex rules, bypassing the LLM classifier completely. The Protect first-hour checklist and verified contacts are served deterministically and work even if the LLM is completely down.
3. **Strict Numeric Grounding**: Every monetary value, count, percentage, and numeral in the assistant's answer must match an exact tool `Fact` or cited evidence chunk text. If any ungrounded number is detected, the system attempts exactly one bounded self-repair; if repair fails, it gracefully degrades to an extractive structured fallback.
4. **Malayalam & Manglish First-Class Support**: The router and grounding validator natively support Malayalam script, Manglish transliterations, Indian numbering terms (`lakh`, `crore`), and Malayalam numerals (`൦`..`൯`).
5. **No Invented Credit Scores**: The credit readiness route enforces indicative readiness assessments (`low`, `fair`, `good`, `strong`). It never invents a numerical credit score or presents itself as an official loan approval/rejection.
6. **No Raw Text in Audit Logs**: Audit trail entries record execution metadata only (route, latency, facts count, evidence count, validation outcomes, degraded status); raw user questions and LLM prompts are never written to audit tables.

---

## 2. Package Architecture

```
apps/api/app/ai/agent/
├── __init__.py               # Package exports
├── models.py                 # RouteClass, AgentState, RouteResult, ToolCallSpec, OrchestratorPlan, AssistantChatRequest/Response
├── router.py                 # Layered IntentRouter (Safety overrides, rules, language detection, LLM fallback)
├── numeric_grounding.py      # NumericGroundingValidator, Indian/Malayalam numeral parser, Fact matching
├── composer.py               # ResponseComposer (delimited prompt blocks) and build_structured_fallback
├── orchestrator.py           # AssistantOrchestrator state machine
└── dependencies.py           # FastAPI dependency injection helpers

apps/api/app/api/v1/
└── assistant.py              # POST /api/v1/assistant/chat endpoint
```

---

## 3. Empirical Results & Confidence Intervals

### A) Intent Router Evaluation on Multilingual Test Set
Evaluated against `tests/ai/routing_test_dataset.py`, consisting of **115 realistic labeled queries** across English (`en`), Malayalam (`ml`), and Manglish:

| Metric | Result | 95% Confidence Interval (Wilson Score) | Target / Requirement | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Overall Classification Accuracy** | **93.91%** (108/115) | **[87.97%, 97.02%]** | >= 90.0% | **PASSED** |
| **Protect Safety Recall** | **100.00%** (26/26) | **[87.13%, 100.00%]** | **100.0% (Zero misclassifications)** | **PASSED** |
| English Accuracy | 95.83% (46/48) | [86.02%, 98.85%] | >= 90.0% | **PASSED** |
| Malayalam Accuracy | 94.29% (33/35) | [81.38%, 98.47%] | >= 90.0% | **PASSED** |
| Manglish Accuracy | 90.62% (29/32) | [75.79%, 96.76%] | >= 85.0% | **PASSED** |

### Breakdown by Route Class
- `protect`: **26/26 (100.0%)** (zero fraud queries missed)
- `personal_finance`: **19/20 (95.0%)**
- `knowledge`: **15/16 (93.8%)**
- `credit_readiness`: **15/16 (93.8%)**
- `combined`: **11/12 (91.7%)**
- `out_of_scope`: **12/13 (92.3%)**
- `unclear`: **10/12 (83.3%)**

---

## 4. Test Suite Verification

All **210 automated unit and integration tests** across `apps/api` pass cleanly:
- `tests/ai/test_agent_orchestrator.py`: 16 comprehensive tests verifying:
  - Multilingual router accuracy and 100% protect safety override.
  - Template clarification questions on unclear queries (no infinite loop).
  - Polite localized refusals on out-of-scope queries (stocks, crypto, tax filing).
  - Numeric grounding accepting exact facts, lakh/crore formats, and Malayalam numerals (`൨൫,൦൦൦`).
  - Numeric grounding rejecting hallucinations (e.g., hallucinated ₹45,000 when facts only state ₹30,000).
  - Strict consent enforcement (403 Forbidden without `ai_data_processing` consent).
  - Indicative borrow readiness validation (zero invented numerical scores).
  - Degraded mode fallback when LLM gateway is down or produces ungrounded numbers.
  - Prompt injection boundary defense in user inputs.
  - Full API integration test with database and auth tokens on `POST /api/v1/assistant/chat`.

---

## 5. Architectural Decisions for User Confirmation

### 1. SSE Streaming Postponement
- **Decision**: SSE (Server-Sent Events) token streaming is deliberately omitted from v1.
- **Rationale**: Strict numeric grounding and policy validation cannot validate partial tokens. If streaming is enabled, a hallucinated balance or illegal tax recommendation would be rendered in the user's browser before the validator can reject it. Full answer validation + deterministic fallback requires completing the generation before dispatching to the client.
- **Latency Impact**: With small, focused models (e.g., Gemini Flash / multilingual-e5), complete answer generation and validation finishes in < 800ms.

### 2. Unclear / Ambiguous Query Clarification Policy
- **Decision**: Any single-word or ambiguous greeting/query immediately returns `RouteClass.UNCLEAR` with a localized template asking for clarification (e.g., *"How can I help you today? I can help you analyze spending, review recurring bills, check loan readiness, or report suspicious transactions."*).
- **Rationale**: Prevents hallucinated interpretations of vague inputs and bounds clarification to exactly one turn without conversational loops.

### 3. Extractive Structured Fallback over Generic Failure
- **Decision**: When the LLM gateway is degraded, unreachable, or repeatedly fails numeric grounding validation, the orchestrator does not return a generic "An error occurred" 500 error. Instead, it extracts the deterministic `Fact` objects from tools directly into a clean, formatted Markdown summary.
- **Rationale**: Users still get their verified bank balances and spending totals even during upstream LLM outages.

---

## 6. Known Gaps and Deferred Work (Phase 7 & 8)

1. **Multi-Turn Context Window Pruning**: Current implementation accepts `conversation_id`; full conversation history sliding-window compaction across > 6 turns is slated for Phase 8 hardening.
2. **HNSW vs Exact Scan Benchmark**: Phase 7 will measure real ANN recall against exact vector scan on postgres pgvector before enabling HNSW indexing.
3. **Evaluation Framework (Phase 7)**: Automated golden set evaluation harness for retrieval NDCG, answer faithfulness, and adversarial red-teaming.

---

## 7. Commands to Reproduce Verification

Run these commands inside `d:\PersonalFinanceAgent\apps\api`:

```bash
# 1. Static Lint & Style Check
..\..\venv\Scripts\ruff check app tests

# 2. Type Checking
..\..\venv\Scripts\mypy app --ignore-missing-imports

# 3. Phase 6 Agent Orchestrator Tests
..\..\venv\Scripts\pytest tests/ai/test_agent_orchestrator.py -v

# 4. Entire Test Suite (210 tests)
..\..\venv\Scripts\pytest -q
```
