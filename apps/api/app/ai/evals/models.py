from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

CaseType = Literal[
    "answerable",
    "insufficient_evidence",
    "refusal_expected",
    "tool_test",
    "routing_test",
    "security_test",
]
CaseLanguage = Literal["en", "ml", "manglish"]
CaseStatus = Literal["reviewed", "draft", "human_reviewed"]
CaseSplit = Literal["dev", "test"]


class EvalCase(BaseModel):
    id: str = Field(..., pattern=r"^[a-zA-Z0-9_\-\.]+$")
    question: str
    language: CaseLanguage
    type: CaseType
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    author: str = "rag-eval-team"
    status: CaseStatus = "reviewed"
    split: CaseSplit = "dev"


class MetricSummary(BaseModel):
    mean: float
    ci_95_low: float
    ci_95_high: float
    sample_size: int
    is_indicative: bool = False

    @model_validator(mode="after")
    def flag_indicative(self) -> "MetricSummary":
        if self.sample_size < 30:
            self.is_indicative = True
        return self


class MetricWithCI(BaseModel):
    metric_name: str
    mean: float
    ci_95_low: float
    ci_95_high: float
    sample_size: int
    target: float | None = None
    target_met: bool | None = None
    is_indicative: bool = False
    unit: str = "%"


class EvalMetricResult(BaseModel):
    recall_at_5: MetricSummary
    recall_at_10: MetricSummary
    mrr: MetricSummary
    ndcg_at_5: MetricSummary
    hit_rate: MetricSummary
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    degraded_share: float = 0.0
    sample_size: int = 0


class AbstentionEvaluation(BaseModel):
    threshold: float
    false_abstain_rate: float
    false_answer_rate: float
    answerable_scores: list[float] = Field(default_factory=list)
    insufficient_scores: list[float] = Field(default_factory=list)


class RetrievalEvalReport(BaseModel):
    dataset_version: str
    dataset_hash: str
    config_hash: str
    retrieval_config: dict[str, Any]
    overall: EvalMetricResult
    by_language: dict[str, EvalMetricResult]
    by_type: dict[str, EvalMetricResult]
    worst_questions: list[dict[str, Any]] = Field(default_factory=list)
    abstention_analysis: AbstentionEvaluation | None = None
    warnings: list[str] = Field(default_factory=list)


class UnifiedEvalCase(BaseModel):
    """Unified evaluation test case format across all 6 test suites."""

    id: str
    language: CaseLanguage = "en"
    type: str = "answerable"
    inputs: dict[str, Any] = Field(default_factory=dict)
    fixture_reference: str = "none"
    expected_route: str | None = None
    expected_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    expected_facts: list[dict[str, Any]] = Field(default_factory=list)
    expected_evidence_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_status: str | None = None
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    review_status: str = "human_reviewed"
    needs_native_review: bool = False
    split: CaseSplit = "dev"
    notes: str = ""

    # Convenience accessor for question if specified top-level or in inputs
    question: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_case(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize status / review_status
            if "status" in data and "review_status" not in data:
                st = data["status"]
                data["review_status"] = "human_reviewed" if st == "reviewed" else st
            # Normalize question
            if "question" in data and "inputs" not in data:
                data["inputs"] = {"question": data["question"]}
            elif "inputs" in data and "question" in data["inputs"] and "question" not in data:
                data["question"] = data["inputs"]["question"]
            # Mark native review needed for ml and manglish
            lang = data.get("language")
            if lang in ("ml", "manglish") and "needs_native_review" not in data:
                data["needs_native_review"] = True
        return data


class SuiteEvaluationResult(BaseModel):
    suite_name: str
    passed: bool
    sample_size: int
    metrics: dict[str, MetricWithCI]
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    token_usage: dict[str, int] = Field(default_factory=dict)
    retries: int = 0
    failures: list[dict[str, Any]] = Field(default_factory=list)
    security_violations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ComprehensiveReport(BaseModel):
    timestamp: str
    git_commit: str
    provider: str
    model: str
    embedding_model: str
    prompt_version: str
    dataset_versions: dict[str, str]
    overall_passed: bool
    suites: dict[str, SuiteEvaluationResult]
    targets: dict[str, dict[str, Any]]
    regression_comparison: dict[str, Any] | None = None
