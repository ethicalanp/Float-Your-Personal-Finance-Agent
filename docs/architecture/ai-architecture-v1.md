# Float AI & RAG Architecture Specification (v1)

- **Status**: Proposed / Under Review (Phase 0)
- **Target Subsystem**: `app/ai/`
- **Authors**: Senior ML / MLOps Engineer
- **Branch**: `feat/ai-llm-rag`

---

## 1. Executive Summary & Core Principles

The Float AI system adds an intelligent conversational interface over personal financial intelligence (**Plan**), scam detection & recovery (**Protect**), and indicative credit readiness (**Borrow**). 

The design is governed by two bedrock architectural premises:
1. **AI is an Enhancement, Never a Hard Dependency**: If the external LLM provider, vector database, or gateway degrades or fails (503/timeout), core deterministic domain services (rule-based scam heuristics, bank statement parsing, recovery case checklists, national helpline contacts) must continue to function normally without degradation.
2. **Deterministic Data Boundaries & Hard Safety Invariants**: The LLM is an untrusted reasoning and natural-language formatting component. It is never given raw database handles, direct SQL access, or internal ML model weights.

---

## 2. The Eight Hard Rules

These rules must never be violated in code, prompts, or configuration. Every rule is accompanied by mandatory automated regression tests.

| Rule # | Invariant | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Rule 1** | **No Direct Database or Internal Model Access** | The LLM operates solely by issuing typed, schema-validated tool calls. Tools return serialized JSON data. No SQLAlchemy session, SQL query text, or ML estimator objects are exposed to tool definitions. |
| **Rule 2** | **Context-Bound User Identity** | User identity is strictly derived from the authenticated request context (`CurrentUser` from verified JWT). Tool schemas must **NOT** accept a `user_id` parameter. |
| **Rule 3** | **Data is Untrusted Data, Never Instructions** | User messages, transaction remarks, merchant names, SMS text, and retrieved knowledge chunks are framed in isolated data delimiters (`<data>...</data>`). System prompts explicitly instruct the LLM to ignore control directives embedded in data fields. |
| **Rule 4** | **No LLM Mental Arithmetic on Money** | Every calculation (totals, category sums, debt-to-income ratios, day counts) must be computed deterministically by verified tools. The LLM is prohibited from calculating financial sums or balances in its head. |
| **Rule 5** | **Pre-Egress PII Masking & Clean Logging** | All user inputs and financial descriptions pass through `mask_sensitive_data()` before leaving the API boundary. Raw account numbers, card numbers, OTPs, passwords, and phone numbers are scrubbed from LLM prompts and application logs. |
| **Rule 6** | **Graceful Degradation** | Complete LLM gateway outage degrades to existing deterministic API endpoints. Plan cash-flow views, Protect rule checks, and Borrow readiness remain 100% operational. |
| **Rule 7** | **Indicative Borrow Readiness Only** | Borrow answers are explicitly communicated as *indicative readiness* with plain-language reasons. If the ML Borrow model returns 503 or is unapproved/unavailable, the system returns a plain status message. The LLM must never invent a credit score. |
| **Rule 8** | **Read-Only Actions in v1 (No Automated Side-Effects)** | In v1, all agent tools are strictly read-only. Actionable outputs (e.g. cybercrime complaint drafts) are generated as proposals/drafts returned to the user for explicit review and confirmation. |

---

## 3. Modular Monolith Architecture (`app/ai/`)

The subsystem lives in `app/ai/` as self-contained sub-packages that can be developed, tested, and imported independently:

```
apps/api/app/ai/
├── __init__.py
├── gateway/          # Provider-agnostic LLM client (OpenAI, Anthropic, Gemini, local)
│   ├── base.py       # Abstract BaseGateway, CompletionRequest, StreamingChunk
│   ├── providers/    # Concrete adapters (litellm / direct clients)
│   └── resilience.py # Circuit breaker, retry with backoff, token tracking
├── rag/              # Retrieval-Augmented Generation pipeline
│   ├── embedder.py   # Multilingual embedding generator (intfloat/multilingual-e5-base)
│   ├── chunker.py    # Structure-aware chunking (Markdown, Circulars, FAQ tables)
│   ├── retriever.py  # Hybrid dense + sparse search (pgvector + FTS / trigram)
│   ├── fusion.py     # Reciprocal Rank Fusion (RRF)
│   └── reranker.py   # Optional Cross-Encoder reranker (feature-flagged)
├── tools/            # Named, typed, read-only domain tools
│   ├── registry.py   # Tool registry and JSON schema generator
│   ├── plan.py       # GetCashFlowSummary, GetRecurringExpenses, GetAccounts
│   ├── protect.py    # CheckScamMessage, GetHelplineContacts, DraftComplaintPreview
│   └── borrow.py     # GetBorrowReadinessStatus
├── agent/            # Conversational orchestrator
│   ├── controller.py # Single-turn & bounded multi-turn tool calling loop
│   ├── context.py    # Conversation state, token budgeting, message pruning
│   └── prompts.py    # System instructions, strict format guards, anti-jailbreak
├── security/         # Security and privacy guardrails
│   ├── sanitizer.py  # Pre-LLM PII masking (integration with app.services.data_sanitizer)
│   ├── validator.py  # Tool call argument schema validator & arithmetic checker
│   └── guardrails.py # Prompt injection detection & untrusted data wrapping
└── evals/            # Offline evaluation and test harnesses
    ├── datasets/     # Curated bilingual evaluation queries (EN, ML, Manglish)
    ├── retrieval.py  # HitRate@K, MRR@K, NDCG@K evaluators
    └── quality.py    # Faithfulness, hallucination detection, tool-call accuracy
```

---

## 4. The Three Query Paths

The orchestrator routes requests through one of three deterministic execution paths:

```
                        User Message (Authenticated Request)
                                      │
                                      ▼
                        [Security: PII Masking]
                                      │
                                      ▼
                           [Intent & Tool Routing]
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
   Path 1: Tools Only           Path 2: RAG Only          Path 3: Combined
 (Personal Financial Data)    (Domain Knowledge Base)  (Hybrid Data & Knowledge)
         │                            │                            │
         ▼                            ▼                            ▼
 - Plan: Cashflow / SMS      - RBI Regulations / Rules    - "I sent money to an
 - Protect: Verify Contacts  - First-hour procedures        electricity bill APK;
 - Borrow: Readiness status  - Scam pattern library         what did I lose and
         │                            │                     what is my status?"
         └────────────────────────────┼────────────────────────────┘
                                      │
                                      ▼
                       [Grounded Response Synthesis]
                                      │
                                      ▼
               [Security: Arithmetic Guard & Output Validation]
                                      │
                                      ▼
                           Safe Response to Client
```

### Path 1: Personal Data via Tools
- **Use Case**: User inquires about their own finances (*"How much did I spend on food this month?"*, *"What recurring payments do I have next week?"*).
- **Execution Flow**:
  1. System extracts user intent and identifies required read-only tool (`get_cash_flow_summary`).
  2. Orchestrator executes tool internally passing `current_user.id` (hidden from LLM schema).
  3. Tool returns structured, aggregated JSON.
  4. LLM formats natural language answer citing exact figures returned by the tool.

### Path 2: Knowledge via RAG
- **Use Case**: General regulatory or financial security guidance (*"What are the RBI rules on compensation for delayed transaction reversals?"*, *"How does helpline 1930 work?"*).
- **Execution Flow**:
  1. User query is sanitized and embedded via `embedder.py` with `"query: "` prefix.
  2. Sparse keyword query is generated.
  3. Hybrid retrieval performs dense cosine search against `knowledge_chunks` + full-text search.
  4. Top-$k$ chunks are fused via RRF (and optional reranker).
  5. Retrieved passages are enclosed in `<data>` tags and sent to LLM for grounded synthesis with source citations.

### Path 3: Combined Path (Personal Data + RAG)
- **Use Case**: Contextual situational queries (*"I received an SMS about bill disconnection and paid ₹2,500. Was that a scam, what was my account balance impact, and how do I complain?"*).
- **Execution Flow**:
  1. Orchestrator executes Protect scam heuristics tool (`check_scam_message`) and Plan transaction tool (`get_recent_transactions`).
  2. Orchestrator retrieves official knowledge chunks on electricity cyber fraud and bank chargeback rules.
  3. Both sets of structured data are provided to the LLM.
  4. LLM produces a unified response: verified threat analysis, actual verified deduction confirmation, recovery steps, and a formal complaint draft preview.

---

## 5. Database Schema Alignment & Existing Models

### 1. `knowledge_documents` & `knowledge_chunks` (`app/models/knowledge.py`)
- `knowledge_documents`: Holds metadata, publisher, source URL, and document version.
- `knowledge_chunks`:
  - `embedding`: Currently configured as `Vector(768)`.
  - `embedding_model`: Stored per chunk as `String(128)`.
  - `content_tsv`: Generated via `Computed("to_tsvector('english'::regconfig, content)", persisted=True)`.
  - Indices: GIN index on `content_tsv`, HNSW cosine index on `embedding`.
- **Architectural Observations**:
  - The 768-dimension column perfectly accommodates modern high-performing multilingual embeddings (e.g. `intfloat/multilingual-e5-base`).
  - The `'english'` regconfig on `content_tsv` strips non-Latin stems and is inadequate for Malayalam and Manglish; evaluated in ADR-002.

### 2. `conversations` & `messages` (`app/models/conversations.py`)
- `conversations`: Scoped to `user_id` with composite unique index `(id, user_id)` and timestamp tracking.
- `messages`:
  - Composite foreign key references `(conversation_id, user_id)`.
  - `content_masked`: Raw text is never persisted unmasked.
  - `tool_calls`: Stores JSON execution audit (tool name, inputs, validated outputs).
  - `trace_id`: Distributed trace identifier linked to observability.

---

## 6. Failure Modes & Graceful Degradation Strategy

| Failure Scenario | Detection | Fallback / User Experience |
| :--- | :--- | :--- |
| **External LLM Gateway 503 / Timeout** | Circuit breaker opens on 3 consecutive timeouts / 5xx | System returns pre-composed fallback: *"Our AI conversational assistant is temporarily unavailable. Your core Plan, Protect, and Borrow dashboards remain fully active."* Directly links to `/protect` and `/plan`. |
| **RAG Retrieval Failure / Database Timeout** | Vector query timeout (> 500ms) | RAG drops to sparse-only or rule-based FAQ fallback. LLM is informed: *"No authoritative knowledge base articles found. State only known facts or advise checking official bank contacts."* |
| **Tool Execution Error** | Tool raises exception or timeout | LLM receives error block: `<tool_error>Unable to retrieve transactions</tool_error>`. LLM reports: *"I was unable to load your latest transactions right now. Please check your Accounts tab."* LLM does not speculate on values. |
| **Prompt Injection in Message / Data** | Guardrail filters or delimiter breaks | The model is explicitly prompted that `<data>` blocks contain passive strings. If an injection attempt is detected, query is flagged in audit trail and answered neutrally. |
| **Borrow Model 503 / Not Ready** | Tool returns `{ "status": "unavailable", "code": 503 }` | Answer explicitly quotes: *"Borrow readiness assessment is currently undergoing calibration and is unavailable. Float does not estimate credit scores."* |

---

## 7. Open Questions for Product & Tech Alignment

1. **LLM Deployment Model**: Do we prioritize a hosted zero-retention API provider (e.g., Anthropic Claude 3.5 Haiku / Sonnet via AWS Bedrock or OpenAI via Azure with zero data retention agreement) or an on-premise/self-hosted vLLM instance in India (e.g. Qwen 2.5 72B / Llama 3.1) for strict regulatory residency?
2. **Context Window & Chat Retention Policy**: How many historical turns should be included in prompt context (e.g. last 6 turns / 2,000 tokens), and after how many days should inactive conversation records be archived?
3. **Draft Complaint Actions**: When a user reviews a complaint draft in v1, should the interface provide a 1-click "Download PDF/Email Draft" button, or copy-to-clipboard only?
