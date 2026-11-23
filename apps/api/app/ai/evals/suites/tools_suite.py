import time
from typing import Any

from app.ai.evals.metrics import summarize_metric_with_ci
from app.ai.evals.models import SuiteEvaluationResult
from app.ai.evals.suites.common import create_eval_db_session, load_unified_dataset
from app.ai.tools.base import ToolContext
from app.ai.tools.errors import ToolError
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.financial_tools import register_financial_tools
from app.ai.tools.registry import default_registry


async def run_tools_suite(include_drafts: bool = False) -> SuiteEvaluationResult:
    cases = load_unified_dataset("finance_tools_v1.jsonl", include_drafts=include_drafts)
    session, primary_user, _ = await create_eval_db_session()

    # Register financial tools
    register_financial_tools()
    executor = ToolExecutor(registry=default_registry)

    ctx = ToolContext(
        user_id=primary_user.id,
        request_id="eval-tool-req",
        session=session,
        locale="en_IN",
        timezone="Asia/Kolkata",
    )

    exact_matches: list[float] = []
    latencies: list[float] = []
    failures: list[dict[str, Any]] = []

    for case in cases:
        t0 = time.monotonic()
        tool_name = case.inputs.get("tool_name", "")
        args = case.inputs.get("arguments", {})

        is_refusal_expected = case.type == "refusal_expected"
        try:
            result = await executor.execute(tool_name, args, ctx)
            dur_ms = (time.monotonic() - t0) * 1000
            latencies.append(dur_ms)

            if is_refusal_expected:
                failures.append({
                    "id": case.id,
                    "reason": "Expected tool failure/refusal, but execution succeeded",
                })
                exact_matches.append(0.0)
                continue

            if not result.ok:
                failures.append({
                    "id": case.id,
                    "reason": f"Tool execution failed: {result.warnings}",
                })
                exact_matches.append(0.0)
                continue

            # Verify exact matches for expected facts
            case_matched = True
            result_facts = {f.id: f for f in result.facts}
            for exp in case.expected_facts:
                fid = exp.get("id")
                exp_val = exp.get("value")
                exp_unit = exp.get("unit")

                if fid not in result_facts:
                    case_matched = False
                    failures.append({
                        "id": case.id,
                        "reason": f"Missing expected fact '{fid}'",
                    })
                    break

                act = result_facts[fid]
                if act.value != exp_val or (exp_unit and act.unit != exp_unit):
                    case_matched = False
                    failures.append({
                        "id": case.id,
                        "reason": f"Fact mismatch for {fid}: expected {exp_val} {exp_unit}, got {act.value} {act.unit}",
                    })
                    break

            exact_matches.append(1.0 if case_matched else 0.0)

        except ToolError as e:
            dur_ms = (time.monotonic() - t0) * 1000
            latencies.append(dur_ms)
            if is_refusal_expected:
                # Expected refusal occurred
                exact_matches.append(1.0)
            else:
                failures.append({"id": case.id, "reason": f"Unexpected ToolError: {e.code}: {e.message}"})
                exact_matches.append(0.0)
        except Exception as e:
            dur_ms = (time.monotonic() - t0) * 1000
            latencies.append(dur_ms)
            if is_refusal_expected:
                exact_matches.append(1.0)
            else:
                failures.append({"id": case.id, "reason": f"Unexpected exception: {str(e)}"})
                exact_matches.append(0.0)

    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    fin_correctness = summarize_metric_with_ci(
        name="financial_correctness",
        values=exact_matches,
        target=1.0,
        higher_is_better=True,
    )

    passed = len(failures) == 0 and fin_correctness.mean == 1.0

    return SuiteEvaluationResult(
        suite_name="finance_tools",
        passed=passed,
        sample_size=len(cases),
        metrics={"financial_correctness": fin_correctness},
        latency_p50_ms=round(p50, 2),
        latency_p95_ms=round(p95, 2),
        failures=failures,
    )
