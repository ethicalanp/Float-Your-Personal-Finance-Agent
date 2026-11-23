import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.ai.evals.models import ComprehensiveReport, MetricWithCI, SuiteEvaluationResult
from app.ai.evals.suites import (
    run_agent_suite,
    run_answers_suite,
    run_combined_suite,
    run_rag_suite,
    run_routing_suite,
    run_security_suite,
    run_tools_suite,
)
from app.ai.gateway.adapters.fake import FakeProvider
from app.ai.gateway.config import LLMConfig
from app.ai.gateway.dependencies import get_llm_gateway
from app.ai.gateway.manager import LLMGateway

# Load .env for local configured provider runs
load_dotenv(".env")
load_dotenv("../../.env")


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()[:10]
    except Exception:
        return "unknown"


def build_markdown_report(report: ComprehensiveReport) -> str:
    lines = [
        f"# AI Evaluation Report - {report.timestamp}",
        f"\n**Git Commit**: `{report.git_commit}` | **Provider**: `{report.provider}` | "
        f"**Model**: `{report.model}` | **Overall Status**: "
        f"{'✅ **PASSED**' if report.overall_passed else '❌ **FAILED**'}\n",
        "## 1. Engineering Targets Summary",
        "\n| Target Metric | Required Target | Measured Mean | 95% Bootstrap CI | Sample Size (n) | Target Met? |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for t_name, data in report.targets.items():
        req = data.get("required", "N/A")
        mean = data.get("mean")
        ci_str = data.get("ci_95", "N/A")
        n = data.get("sample_size", 0)
        met = data.get("target_met")

        mean_str = f"{mean:.2%}" if isinstance(mean, float) else str(mean)
        met_str = "✅ YES" if met else ("❌ NO" if met is False else "—")
        indicative_tag = " *(indicative, n < 30)*" if n < 30 else ""

        lines.append(f"| `{t_name}` | {req} | **{mean_str}**{indicative_tag} | {ci_str} | {n} | {met_str} |")

    lines.append("\n## 2. Evaluation Suite Results\n")
    for s_name, s_res in report.suites.items():
        status_icon = "✅ PASSED" if s_res.passed else "❌ FAILED"
        lines.append(f"### Suite: `{s_name}` ({status_icon})")
        lines.append(f"- **Sample Size**: {s_res.sample_size}")
        lines.append(f"- **Latency**: P50 = {s_res.latency_p50_ms:.1f}ms, P95 = {s_res.latency_p95_ms:.1f}ms")

        if s_res.metrics:
            lines.append("\n| Metric | Mean | 95% CI | Target | Status |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for m_name, m_val in s_res.metrics.items():
                m_mean = f"{m_val.mean:.2%}"
                m_ci = f"[{m_val.ci_95_low:.2%}, {m_val.ci_95_high:.2%}]"
                m_target = f"{m_val.target:.2%}" if m_val.target is not None else "—"
                m_met = "✅ PASSED" if m_val.target_met else ("❌ FAILED" if m_val.target_met is False else "—")
                lines.append(f"| `{m_name}` | {m_mean} | {m_ci} | {m_target} | {m_met} |")

        if s_res.security_violations:
            lines.append("\n> [!CAUTION]")
            lines.append(f"> **{len(s_res.security_violations)} SECURITY VIOLATIONS DETECTED:**")
            for v in s_res.security_violations:
                lines.append(f"> - **[{v.get('category')}]** {v.get('id')}: {v.get('detail')}")

        if s_res.failures and not s_res.security_violations:
            lines.append(f"\n*Failures ({len(s_res.failures)})*:")
            for f in s_res.failures[:5]:
                lines.append(f"- Case `{f.get('id')}`: {f.get('reason') or f.get('got')}")
        lines.append("\n---")

    if report.regression_comparison:
        lines.append("\n## 3. Regression Analysis vs Previous Run")
        reg = report.regression_comparison
        lines.append(f"Comparing with: `{reg.get('previous_file')}`")
        if reg.get("regressions_detected"):
            lines.append("\n> [!WARNING]\n> **REGRESSIONS DETECTED:**")
            for r in reg.get("regressions", []):
                lines.append(f"> - Metric `{r['metric']}` dropped from {r['prev']:.2%} to {r['curr']:.2%}")
        else:
            lines.append(
                "\n✅ **No regressions detected. All metrics maintained or improved within confidence intervals.**"
            )

    return "\n".join(lines)


def check_regression(
    current_metrics: dict[str, MetricWithCI],
    previous_path: Path,
) -> dict[str, Any]:
    if not previous_path.exists():
        return {"previous_file": str(previous_path), "error": "Previous report not found"}

    with open(previous_path, encoding="utf-8") as f:
        prev_data = json.load(f)

    regressions = []
    prev_targets = prev_data.get("targets", {})

    for metric_name, curr in current_metrics.items():
        if metric_name in prev_targets:
            prev_mean = prev_targets[metric_name].get("mean", 0.0)
            # Regression rule: A drop outside the 95% confidence interval fails
            if curr.ci_95_high < prev_mean:
                regressions.append({
                    "metric": metric_name,
                    "prev": prev_mean,
                    "curr": curr.mean,
                    "curr_ci": [curr.ci_95_low, curr.ci_95_high],
                })

    return {
        "previous_file": str(previous_path),
        "regressions_detected": len(regressions) > 0,
        "regressions": regressions,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Float AI Evaluation Suite Runner")
    parser.add_argument(
        "--suite",
        choices=["tools", "rag", "answers", "combined", "routing", "security", "agent", "all"],
        default="all",
        help="Which evaluation suite to run",
    )
    parser.add_argument(
        "--provider",
        choices=["fake", "configured"],
        default="fake",
        help="LLM provider: fake (for deterministic CI) or configured (local keys from .env)",
    )
    parser.add_argument(
        "--compare",
        type=str,
        default=None,
        help="Path to previous JSON report to evaluate regressions",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="evals/reports",
        help="Directory to save generated JSON and markdown reports",
    )
    args = parser.parse_args()

    # Determine provider and gateway
    if args.provider == "fake":
        gateway = LLMGateway(
            config=LLMConfig(provider="fake", approved_for_real_data=True),
            adapter=FakeProvider(),
        )
        provider_name = "fake"
        model_name = "fake-eval-v1"
    else:
        # Configured provider (e.g. Groq / Gemini from .env)
        try:
            gateway = get_llm_gateway()
            provider_name = gateway.config.provider
            model_name = gateway.config.model
        except Exception as e:
            print(f"Failed to initialize configured LLM gateway: {e}. Falling back to FakeProvider.")
            gateway = LLMGateway(
                config=LLMConfig(provider="fake", approved_for_real_data=True),
                adapter=FakeProvider(),
            )
            provider_name = "fake"
            model_name = "fake-fallback"

    suites_to_run = (
        ["tools", "routing", "rag", "answers", "combined", "security", "agent"]
        if args.suite == "all"
        else [args.suite]
    )

    results: dict[str, SuiteEvaluationResult] = {}
    print("\n==================================================================")
    print(f"FLOAT AI EVALUATION HARNESS: Running suite(s) '{args.suite}' with provider '{provider_name}'")
    print("==================================================================\n")

    for s in suites_to_run:
        print(f"--> Running suite: {s} ...", end=" ", flush=True)
        t_start = time.monotonic()
        if s == "tools":
            res = await run_tools_suite()
        elif s == "routing":
            res = await run_routing_suite(gateway=gateway)
        elif s == "rag":
            res = await run_rag_suite()
        elif s == "answers":
            res = await run_answers_suite(gateway=gateway)
        elif s == "combined":
            res = await run_combined_suite(gateway=gateway)
        elif s == "security":
            res = await run_security_suite(gateway=gateway)
        elif s == "agent":
            res = await run_agent_suite(gateway=gateway)
        else:
            continue

        dur = time.monotonic() - t_start
        status_label = "PASSED" if res.passed else "FAILED"
        print(f"[{status_label}] ({dur:.2f}s, n={res.sample_size})")
        results[s] = res

    # Gather metrics across suites for engineering targets
    all_metrics: dict[str, MetricWithCI] = {}
    for s_res in results.values():
        all_metrics.update(s_res.metrics)

    def _format_ci(m: MetricWithCI | None) -> str:
        return f"[{m.ci_95_low:.2%}, {m.ci_95_high:.2%}]" if m else "N/A"

    targets = {
        "financial_correctness": {
            "required": "100.0%",
            "mean": all_metrics["financial_correctness"].mean if "financial_correctness" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("financial_correctness")),
            "sample_size": all_metrics["financial_correctness"].sample_size
            if "financial_correctness" in all_metrics else 0,
            "target_met": all_metrics["financial_correctness"].target_met
            if "financial_correctness" in all_metrics else None,
        },
        "cross_user_blocked": {
            "required": "100.0%",
            "mean": all_metrics["cross_user_blocked"].mean if "cross_user_blocked" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("cross_user_blocked")),
            "sample_size": all_metrics["cross_user_blocked"].sample_size
            if "cross_user_blocked" in all_metrics else 0,
            "target_met": all_metrics["cross_user_blocked"].target_met
            if "cross_user_blocked" in all_metrics else None,
        },
        "pii_masking": {
            "required": "100.0%",
            "mean": all_metrics["pii_masking"].mean if "pii_masking" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("pii_masking")),
            "sample_size": all_metrics["pii_masking"].sample_size if "pii_masking" in all_metrics else 0,
            "target_met": all_metrics["pii_masking"].target_met if "pii_masking" in all_metrics else None,
        },
        "citation_validity": {
            "required": "100.0%",
            "mean": all_metrics["citation_validity"].mean if "citation_validity" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("citation_validity")),
            "sample_size": all_metrics["citation_validity"].sample_size
            if "citation_validity" in all_metrics else 0,
            "target_met": all_metrics["citation_validity"].target_met
            if "citation_validity" in all_metrics else None,
        },
        "invented_contact_rate": {
            "required": "0.0%",
            "mean": all_metrics["invented_contact_rate"].mean if "invented_contact_rate" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("invented_contact_rate")),
            "sample_size": all_metrics["invented_contact_rate"].sample_size
            if "invented_contact_rate" in all_metrics else 0,
            "target_met": all_metrics["invented_contact_rate"].target_met
            if "invented_contact_rate" in all_metrics else None,
        },
        "structured_output_validity": {
            "required": ">= 99.0%",
            "mean": all_metrics["structured_output_validity"].mean
            if "structured_output_validity" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("structured_output_validity")),
            "sample_size": all_metrics["structured_output_validity"].sample_size
            if "structured_output_validity" in all_metrics else 0,
            "target_met": all_metrics["structured_output_validity"].target_met
            if "structured_output_validity" in all_metrics else None,
        },
        "recall_at_5": {
            "required": ">= 85.0%",
            "mean": all_metrics["recall_at_5"].mean if "recall_at_5" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("recall_at_5")),
            "sample_size": all_metrics["recall_at_5"].sample_size if "recall_at_5" in all_metrics else 0,
            "target_met": all_metrics["recall_at_5"].target_met if "recall_at_5" in all_metrics else None,
        },
        "faithfulness": {
            "required": ">= 90.0%",
            "mean": all_metrics["faithfulness"].mean if "faithfulness" in all_metrics else None,
            "ci_95": _format_ci(all_metrics.get("faithfulness")),
            "sample_size": all_metrics["faithfulness"].sample_size if "faithfulness" in all_metrics else 0,
            "target_met": all_metrics["faithfulness"].target_met if "faithfulness" in all_metrics else None,
        },
    }

    # Regression comparison if requested
    regression_info = None
    if args.compare:
        regression_info = check_regression(all_metrics, Path(args.compare))

    # Overall pass criteria
    sec_res = results.get("security")
    security_passed = sec_res.passed if sec_res is not None else True
    all_passed = all(r.passed for r in results.values())
    no_regressions = not (regression_info and regression_info.get("regressions_detected"))
    overall_passed = all_passed and security_passed and no_regressions

    now_iso = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report = ComprehensiveReport(
        timestamp=now_iso,
        git_commit=get_git_commit(),
        provider=provider_name,
        model=model_name,
        embedding_model="multilingual-e5-base",
        prompt_version="composer_v1",
        dataset_versions={
            "finance_tools": "v1",
            "routing": "v1",
            "rag": "v1",
            "answers": "v1",
            "combined": "v1",
            "security": "v1",
        },
        overall_passed=overall_passed,
        suites=results,
        targets=targets,
        regression_comparison=regression_info,
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"eval_report_{provider_name}_{now_iso}.json"
    md_path = out_dir / f"eval_report_{provider_name}_{now_iso}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

    md_content = build_markdown_report(report)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n==================================================================")
    print(f"EVALUATION COMPLETE: Overall Status = {'PASSED' if overall_passed else 'FAILED'}")
    print(f"JSON Report : {json_path}")
    print(f"MD Report   : {md_path}")
    print("==================================================================\n")

    # If security failed or regression detected, exit with code 1
    if not security_passed or not no_regressions:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
