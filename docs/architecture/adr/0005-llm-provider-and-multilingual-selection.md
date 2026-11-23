# ADR-005: LLM Provider Gateway and Multilingual Model Selection

- **Status**: Proposed (Evaluation Protocol Defined)
- **Date**: 2026-11-22
- **Area**: LLM Gateway / Multi-Provider Orchestration

---

## Context

Float serves Indian users who communicate in:
1. **Standard Indian English** (formal banking queries, SMS notifications, transaction questions).
2. **Malayalam script** (`ml` — official announcements, local scam warnings).
3. **Manglish** (colloquial transliterated Malayalam in Latin script, e.g., *"Ente accountil ninnu 2000 roopa poyi, enthu cheyyanam?"*).

Many frontier models that score well on English fail on Manglish (treating it as gibberish, hallucinating English words, or producing unnatural literal Malayalam translations). 

Furthermore, data privacy and regulatory standards dictate that:
- PII must be scrubbed before sending prompts to external APIs.
- The system must support provider fallback (if Provider A is down or rate-limited, fall back to Provider B).
- The gateway must support strict JSON structured outputs and tool calling.

---

## Provider Candidates for Comparison

| Candidate Model | Multilingual Capability (EN / ML / Manglish) | Tool Calling & Structured Output | Typical Latency (TTFT) | Privacy / Data Residency | Cost / 1M Tokens (Input / Output) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Anthropic Claude 3.5 Sonnet / Haiku** | Exceptional nuance; strong on Indian linguistic context and regional script comprehension | Reliable, typed tool use | ~280ms (Haiku), ~650ms (Sonnet) | Zero data retention via AWS Bedrock (Mumbai region available) | $0.80 / $4.00 (Haiku 3.5) |
| **OpenAI GPT-4o / GPT-4o-mini** | Strong general multilingual; good Manglish handling with appropriate few-shot prompts | Native JSON schema enforcement & strict tool call grammar | ~220ms (mini), ~550ms (4o) | Azure OpenAI (India Central/South available with zero-retention) | $0.15 / $0.60 (mini) |
| **Google Gemini 1.5 Flash** | Excellent native tokenization for Indic scripts (efficient byte allocation); high context | Strong function calling | ~200ms | Google Cloud (Mumbai / Delhi regions) | $0.075 / $0.30 |
| **Self-Hosted Open Weights (Qwen 2.5 72B / Llama 3.1 70B via vLLM)** | Qwen 2.5 has top-tier Asian multilingual scores; complete sovereignty | Reliable with outlines / vLLM grammar guides | Dependent on local GPU (A100/H100) | 100% on-premise; zero third-party cloud egress | Infrastructure cost only |

---

## Evaluation Protocol on Small Bilingual Test Set (Phase 2 Gate)

Before hardcoding any single provider as the production default, we will execute a comparison on a **curated 25-prompt bilingual benchmark**:

1. **Test Set Composition**:
   - **8 English Prompts**: Complex transaction explanations, cash-flow summary interpretation, indicative borrowing readiness questions.
   - **9 Malayalam Script Prompts**: Fraud advisory interpretation, formal complaint drafting against unauthorized bank transfers.
   - **8 Manglish Prompts**: Informal distress messages (e.g. *"Electricity bill pay cheyyan paranjappol linkil click aayi, scam aano?"*).
2. **Evaluation Metrics**:
   - **Tool Calling Accuracy**: Did the model select the correct tool (`check_scam_message`, `get_cash_flow_summary`) with valid JSON parameters?
   - **Linguistic Naturalness & Faithfulness**: Evaluated for coherence in English, native Malayalam, and colloquial Manglish (no awkward literal translations).
   - **Arithmetic Invariance**: Verifying that the model quoted exact tool output numbers and performed zero mental arithmetic.
   - **Latency (Time-to-First-Token)**.

---

## Architectural Decision

1. **Implement `app/ai/gateway/` as a Provider-Agnostic Abstraction**:
   - Common interface `BaseGateway` with standardized `generate()`, `stream()`, and `call_tools()`.
   - Pluggable provider adapters (OpenAI-compatible, Anthropic-compatible, Gemini-compatible).
2. **Primary + Automatic Circuit-Breaker Fallback**:
   - Configure a primary provider (e.g., `openai` or `gemini`) and a seamless fallback provider (e.g., `anthropic`) if the primary returns 5xx, 429, or times out.
3. **Decide Production Default via Benchmark**:
   - The final default model selection will be locked in based on empirical results from the Phase 2 bilingual benchmark.

---

## Open Questions for Product Alignment

1. **Data Residency Preference**: Does Float require all model inference to terminate inside India (e.g. AWS Mumbai Bedrock, Azure India Central, or local Indian GPU host), or are global endpoints with zero-retention BAA acceptable in v1?
2. **Budget / Latency Target**: What is the target end-to-end latency budget for conversational responses (e.g., < 1.5 seconds for complete response or streaming first token < 400ms)?
3. **Fallback User Experience**: When both external LLM providers are down, do you prefer a simple deterministic message box offering standard shortcuts, or a conversational rule-based FAQ responder?
