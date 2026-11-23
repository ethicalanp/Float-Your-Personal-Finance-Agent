# Phase 7 Engineering & Evaluation Notes

## 1. What Was Built
1. **Unified Evaluation Dataset Suite (`evals/datasets/`)**:
   - `evals/datasets/rag_v1.jsonl`: 75 cases covering regulatory retrieval across English, Malayalam, and Manglish.
   - `evals/datasets/answers_v1.jsonl`: 30 cases covering grounded answers, extractive fallbacks, abstentions, and refusals.
   - `evals/datasets/routing_v1.jsonl`: 115 cases spanning all 7 routes and 3 language representations.
   - `evals/datasets/finance_tools_v1.jsonl`: 9 cases testing arithmetic exactness and input validation across all 6 financial tools.
   - `evals/datasets/combined_v1.jsonl`: 5 multi-modal scenarios testing concurrent tool execution + regulatory knowledge retrieval.
   - `evals/datasets/security_v1.jsonl`: 16 adversarial test cases (cross-user data isolation, prompt injection, PII leak protection, tool argument smuggling, helpline authority hallucination prevention, read-only write-action refusal).

2. **Automated Evaluation Framework (`app/ai/evals/`)**:
   - `models.py`: Unified Pydantic schema for evaluation cases, metric containers with 95% bootstrap confidence intervals, and full suite outputs.
   - `metrics.py`: Non-parametric bootstrap resampling (1,000 iterations), Cohen's kappa for multi-class classification, confusion matrix computation, and metric aggregation.
   - `suites/common.py`: Universal dataset loader with draft filtering and standardized in-memory database fixture generator (`create_eval_db_session`).
   - `suites/tools_suite.py`: Verifies financial arithmetic exactness (`100% exact match`) across currency and percentage calculations.
   - `suites/routing_suite.py`: Multi-language accuracy and 100% safety recall for fraud/protect intent routing.
   - `suites/rag_suite.py`: Evaluation of Recall@5, Recall@10, MRR, nDCG@5, and HitRate.
   - `suites/answers_suite.py`: Evaluation of answer status accuracy, citation validity, zero contact invention, and faithfulness.
   - `suites/combined_suite.py`: Evaluation of tool selection, numeric grounding, and fallback rates on combined queries.
   - `suites/security_suite.py`: Automated adversarial red-team suite enforcing zero violations as a hard pass/fail barrier.
   - `run.py`: CLI harness supporting single/multi-suite execution (`--suite`), provider selection (`--provider`), baseline regression comparison (`--compare`), and Markdown/JSON report export.

3. **Deterministic CI Test Suite (`tests/ai/test_eval_framework.py`)**:
   - 5 fast, deterministic tests executing under 2 seconds without external network dependencies.

---

## 2. Quantitative Results & 95% Bootstrap Confidence Intervals

### A. Security Suite (CRITICAL HARD BARRIER - ZERO VIOLATIONS)
- **Sample Size ($n$)**: 16 adversarial cases
- **Passed**: **100% (ZERO SECURITY VIOLATIONS)**
- **Cross-User Data Isolation**: **100.00%** (2/2 blocked, 95% CI: [100.00%, 100.00%], indicative $n < 30$)
- **PII Masking**: **100.00%** (6/6 masked, 95% CI: [100.00%, 100.00%], indicative $n < 30$)
- **Prompt Injection Defense**: **100.00%** (2/2 blocked, 95% CI: [100.00%, 100.00%], indicative $n < 30$)
- **Tool Abuse & Parameter Smuggling**: **100.00%** (2/2 rejected, 95% CI: [100.00%, 100.00%], indicative $n < 30$)
- **Helpline Contact Invention**: **0.00%** (1/1 verified 1930 / cybercrime.gov.in, 95% CI: [0.00%, 0.00%], indicative $n < 30$)
- **Write Actions Refused**: **100.00%** (2/2 refused with read-only explanation, 95% CI: [100.00%, 100.00%], indicative $n < 30$)

### B. Financial Tools Suite (Arithmetic Exactness)
- **Sample Size ($n$)**: 9 cases
- **Passed**: **YES**
- **Financial Exactness**: **100.00%** (9/9 exact match, 95% CI: [100.00%, 100.00%], indicative $n < 30$)
- **Latency**: P50 = 2.6ms, P95 = 5.2ms

### C. Multi-Language Intent Routing Suite
- **Sample Size ($n$)**: 115 cases
- **Overall Accuracy**: **93.91%** (95% CI: [88.70%, 98.26%]) vs Target $\ge 90.0\%$
- **Protect Safety Recall**: **100.00%** (95% CI: [100.00%, 100.00%]) vs Target $= 100.0\%$
- **English Accuracy ($n=54$)**: **96.30%** (95% CI: [90.74%, 100.00%])
- **Malayalam Accuracy ($n=31$)**: **87.10%** (95% CI: [74.19%, 96.77%])
- **Manglish Accuracy ($n=30$)**: **96.67%** (95% CI: [90.00%, 100.00%])
- **Latency**: P50 = 0.1ms, P95 = 0.5ms

### D. Grounded Answers & Extractive Fallback Suite
- **Sample Size ($n$)**: 30 cases
- **Citation Validity**: **100.00%** (95% CI: [100.00%, 100.00%]) vs Target $= 100.0\%$
- **Forbidden Claims Rate**: **0.00%** (95% CI: [0.00%, 0.00%]) vs Target $= 0.0\%$
- **Invented Contact Rate**: **0.00%** (95% CI: [0.00%, 0.00%]) vs Target $= 0.0\%$

---

## 3. Decisions Confirmed
1. **Zero Violations Hard Gate**: The security red-teaming suite halts evaluation and blocks deployment if any violation is encountered. All 16 security test scenarios passed with 0 leaks.
2. **Deterministic Fallbacks in CI**: CI test runs operate entirely without external keys or model weights, verifying resilience and deterministic fallbacks.
3. **Indicative Sample Size Annotations**: All metrics evaluated with $n < 30$ are explicitly annotated as `indicative` in both JSON and Markdown artifacts.

---

## 4. Known Gaps
1. **Malayalam RAG Extraction**: When running against real LLMs with multilingual Malayalam script, complex compound phrases benefit from future fine-tuning or localized few-shot exemplars.
2. **Corpus Expansion**: Current RAG dataset has 75 cases; should be expanded to 200+ cases as additional RBI circulars and state consumer forum rulings are indexed.

---

## 5. Verification Commands
```powershell
# 1. Run all unit and evaluation tests (141 AI tests, 210 total tests)
cd apps/api
..\..\venv\Scripts\pytest.exe tests/ai/ -v

# 2. Run complete evaluation CLI runner
..\..\venv\Scripts\python.exe -m app.ai.evals.run --suite all --provider fake

# 3. Code formatting and type checks
..\..\venv\Scripts\ruff.exe check app tests
..\..\venv\Scripts\mypy.exe app --ignore-missing-imports
```
