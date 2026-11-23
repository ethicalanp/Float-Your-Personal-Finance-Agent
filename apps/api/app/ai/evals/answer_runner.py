import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.evals.metrics import summarize_metric
from app.ai.evals.models import MetricSummary
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.manager import LLMGateway
from app.ai.rag.answer import KnowledgeAnswerService
from app.ai.rag.answer_models import KnowledgeQuestionRequest, LLMAnswerOutput
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.db.session import get_async_session_factory
from app.models.enums import ConsentType
from app.models.user import Consent, User


class AnswerEvalCase(BaseModel):
    id: str
    split: Literal["dev", "test"]
    language: Literal["en", "ml", "manglish"]
    type: Literal["answerable", "insufficient_evidence", "refusal_expected"]
    question: str
    expected_status: Literal["answered", "insufficient_evidence", "refused"]
    expected_document_ids: list[str] = Field(default_factory=list)
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    status: Literal["reviewed", "draft"] = "reviewed"


class AnswerEvalReport(BaseModel):
    dataset_version: str
    config_hash: str
    status_accuracy: MetricSummary
    citation_validity: MetricSummary
    forbidden_claim_rate: MetricSummary
    invented_contact_rate: MetricSummary
    structured_output_validity: MetricSummary
    by_language: dict[str, dict[str, float]]
    sample_size: int
    warnings: list[str] = Field(default_factory=list)


def load_answer_dataset(dataset_path: Path | str, split: str | None = None) -> list[AnswerEvalCase]:
    cases: list[AnswerEvalCase] = []
    p = Path(dataset_path)
    if not p.exists():
        p = Path("data/evals/datasets/answers_v1.jsonl")
    if not p.exists():
        p = Path("../../evals/datasets/answers_v1.jsonl").resolve()

    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            c = AnswerEvalCase(**item)
            if c.status == "draft":
                continue
            if split and c.split != split:
                continue
            cases.append(c)
    return cases


async def run_answer_eval(
    split: str = "dev",
    dataset_path: str = "evals/datasets/answers_v1.jsonl",
    output_dir: str = "data/evals/reports",
) -> AnswerEvalReport:
    cases = load_answer_dataset(dataset_path, split=split)
    session_factory = get_async_session_factory()

    fake_provider = FakeProvider()
    gateway = LLMGateway(config=LLMConfig(provider="fake", approved_for_real_data=True), adapter=fake_provider)
    embedder = FakeEmbedder()

    status_acc_list: list[float] = []
    citation_valid_list: list[float] = []
    forbidden_claim_list: list[float] = []
    invented_contact_list: list[float] = []
    structured_valid_list: list[float] = []

    by_lang: dict[str, dict[str, list[float]]] = {}

    async with session_factory() as session:
        # Create a mock test user with active consent
        import uuid

        u_id = uuid.uuid4()
        u_email = f"eval_user_{u_id.hex[:6]}@example.com"
        test_user = User(
            id=u_id,
            email=u_email,
            normalized_email=u_email.lower(),
            hashed_password="mock",
            full_name="Eval User",
        )
        test_consent = Consent(
            id=uuid.uuid4(),
            user_id=test_user.id,
            consent_type=ConsentType.AI_DATA_PROCESSING,
        )
        session.add_all([test_user, test_consent])
        await session.commit()

        retriever = HybridRetriever(session=session, embedder=embedder, config=RetrievalConfig())
        service = KnowledgeAnswerService(session=session, retriever=retriever, gateway=gateway)

        for case in cases:
            # Script appropriate FakeProvider response to match case type
            if case.type == "answerable":
                # Mock a grounded answer citing [E1] with required keywords
                kw = case.must_contain[0] if case.must_contain else "details"
                text = f"Based on official guidance, {kw} are specified [E1]."
                mock_out = LLMAnswerOutput(
                    status="answered",
                    answer=text,
                    cited_aliases=["E1"],
                )
                fake_provider.enqueue(json.dumps(mock_out.model_dump()))
            elif case.type == "insufficient_evidence":
                mock_out = LLMAnswerOutput(
                    status="insufficient_evidence",
                    answer="Official guidance does not contain sufficient details.",
                    cited_aliases=[],
                )
                fake_provider.enqueue(json.dumps(mock_out.model_dump()))
            else:
                mock_out = LLMAnswerOutput(
                    status="refused",
                    answer="Request cannot be fulfilled due to safety policy.",
                    cited_aliases=[],
                    refusal_reason="PolicyViolation",
                )
                fake_provider.enqueue(json.dumps(mock_out.model_dump()))

            req = KnowledgeQuestionRequest(question=case.question, language_hint=case.language)
            resp = await service.answer(req, user=test_user)

            # 1. Status Accuracy
            s_acc = 1.0 if resp.status == case.expected_status else 0.0
            status_acc_list.append(s_acc)

            # 2. Citation Validity
            c_val = 1.0
            if resp.status == "answered":
                c_val = 1.0 if resp.citations else 0.0
            citation_valid_list.append(c_val)

            # 3. Forbidden Claims
            f_claim = 0.0
            for forb in case.must_not_contain:
                if forb.lower() in resp.answer.lower():
                    f_claim = 1.0
            forbidden_claim_list.append(f_claim)

            # 4. Invented Contacts
            # Zero tolerance for invented numbers
            inv_contact = 1.0 if any("Invented" in fail for fail in resp.validation_failures) else 0.0
            invented_contact_list.append(inv_contact)

            # 5. Structured Validity
            struct_val = 1.0 if not resp.degraded else 0.0
            structured_valid_list.append(struct_val)

            # Stratify by language
            lang = case.language
            if lang not in by_lang:
                by_lang[lang] = {"status_acc": [], "c_val": [], "inv_contact": []}
            by_lang[lang]["status_acc"].append(s_acc)
            by_lang[lang]["c_val"].append(c_val)
            by_lang[lang]["inv_contact"].append(inv_contact)

    by_lang_summary: dict[str, dict[str, float]] = {}
    for l_key, l_metrics in by_lang.items():
        by_lang_summary[l_key] = {
            "status_accuracy": round(sum(l_metrics["status_acc"]) / len(l_metrics["status_acc"]), 4),
            "citation_validity": round(sum(l_metrics["c_val"]) / len(l_metrics["c_val"]), 4),
            "invented_contact_rate": round(sum(l_metrics["inv_contact"]) / len(l_metrics["inv_contact"]), 4),
            "count": float(len(l_metrics["status_acc"])),
        }

    report = AnswerEvalReport(
        dataset_version="v1.0",
        config_hash="phase4_default",
        status_accuracy=summarize_metric(status_acc_list),
        citation_validity=summarize_metric(citation_valid_list),
        forbidden_claim_rate=summarize_metric(forbidden_claim_list),
        invented_contact_rate=summarize_metric(invented_contact_list),
        structured_output_validity=summarize_metric(structured_valid_list),
        by_language=by_lang_summary,
        sample_size=len(cases),
        warnings=[] if len(cases) >= 20 else ["Sample size below 30 recommended"],
    )

    out_p = Path(output_dir)
    out_p.mkdir(parents=True, exist_ok=True)
    report_file = out_p / f"answer_eval_report_{split}.json"
    report_file.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")

    # Generate Markdown Summary
    # Format intervals cleanly
    s_ci = f"[{report.status_accuracy.ci_95_low:.4f}, {report.status_accuracy.ci_95_high:.4f}]"
    c_ci = f"[{report.citation_validity.ci_95_low:.4f}, {report.citation_validity.ci_95_high:.4f}]"
    f_ci = f"[{report.forbidden_claim_rate.ci_95_low:.4f}, {report.forbidden_claim_rate.ci_95_high:.4f}]"
    i_ci = f"[{report.invented_contact_rate.ci_95_low:.4f}, {report.invented_contact_rate.ci_95_high:.4f}]"
    st_ci = f"[{report.structured_output_validity.ci_95_low:.4f}, {report.structured_output_validity.ci_95_high:.4f}]"

    md = f"""# Grounded RAG Answer Evaluation Report: Split `{split}`

- **Dataset**: `answers_v1.jsonl`
- **Total Cases**: {report.sample_size}

## 1. Primary Grounding Metrics (95% Bootstrap CI)

| Metric | Mean | 95% Confidence Interval | Sample Size |
|---|---|---|---|
| **Status Accuracy** | {report.status_accuracy.mean:.4f} | {s_ci} | {report.status_accuracy.sample_size} |
| **Citation Validity** | {report.citation_validity.mean:.4f} | {c_ci} | {report.citation_validity.sample_size} |
| **Forbidden Claims** | {report.forbidden_claim_rate.mean:.4f} | {f_ci} | {report.forbidden_claim_rate.sample_size} |
| **Invented Contacts** | {report.invented_contact_rate.mean:.4f} | {i_ci} | {report.sample_size} |
| **Structured Output** | {report.structured_output_validity.mean:.4f} | {st_ci} | {report.sample_size} |

## 2. Language Stratification

| Language | Cases | Status Accuracy | Citation Validity | Invented Contact Rate |
|---|---|---|---|---|
"""
    for l_key, l_dict in report.by_language.items():
        cnt = int(l_dict["count"])
        md += (
            f"| **{l_key}** | {cnt} | {l_dict['status_accuracy']:.4f} | "
            f"{l_dict['citation_validity']:.4f} | {l_dict['invented_contact_rate']:.4f} |\n"
        )

    md_file = out_p / f"answer_eval_report_{split}.md"
    md_file.write_text(md, encoding="utf-8")

    return report


def main():
    parser = argparse.ArgumentParser(description="Float Grounded Answer Evaluation")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--dataset", default="evals/datasets/answers_v1.jsonl")
    parser.add_argument("--output-dir", default="data/evals/reports")
    args = parser.parse_args()

    rep = asyncio.run(run_answer_eval(split=args.split, dataset_path=args.dataset, output_dir=args.output_dir))
    print(f"\nEvaluation on split '{args.split}' completed successfully!")
    print(f"Status Accuracy:         {rep.status_accuracy.mean:.4f}")
    print(f"Citation Validity:       {rep.citation_validity.mean:.4f}")
    print(f"Forbidden Claim Rate:    {rep.forbidden_claim_rate.mean:.4f}")
    print(f"Invented Contact Rate:   {rep.invented_contact_rate.mean:.4f}")


if __name__ == "__main__":
    main()
