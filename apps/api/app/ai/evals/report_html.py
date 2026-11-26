import argparse
import glob
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.ai.evals.report_html")


def generate_html_report(reports_dir: str | Path, output_html_path: str | Path) -> None:
    """Generate a static HTML visualization report from JSON experiment outputs in reports_dir."""
    rep_dir = Path(reports_dir)
    pattern = str(rep_dir / "*.json")
    files = glob.glob(pattern)

    reports: list[dict[str, Any]] = []
    for f in sorted(files):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                reports.append(json.load(fp))
        except Exception as e:
            logger.warning("Could not read report %s: %s", f, e)

    out_file = Path(output_html_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'/>",
        "<title>Float RAG Experiment Report</title>",
        "<style>",
        "body { font-family: sans-serif; margin: 30px; background: #f8fafc; color: #1e293b; }",
        "h1, h2, h3 { color: #0f172a; }",
        ".card { background: #fff; padding: 20px; border-radius: 8px; margin-bottom: 24px; }",
        "table { width: 100%; border-collapse: collapse; margin-top: 12px; }",
        "th, td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; font-size: 14px; }",
        "th { background: #f1f5f9; font-weight: 600; }",
        ".ci { font-size: 12px; color: #64748b; }",
        ".bar-container { background: #e2e8f0; height: 16px; width: 100%; display: inline-block; }",
        ".bar-fill { background: #3b82f6; height: 100%; }",
        ".code-badge { background: #f1f5f9; padding: 2px 6px; font-family: monospace; font-size: 12px; }",
        ".badge-error { background: #fee2e2; color: #991b1b; padding: 2px 6px; font-size: 12px; font-weight: 600; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Float: RAG Experiment Evaluation Dashboard</h1>",
        f"<p>Loaded <strong>{len(reports)}</strong> experiment run reports from <code>{rep_dir}</code></p>",
    ]

    if not reports:
        html_parts.append("<div class='card'><p>No JSON reports found in reports directory.</p></div>")
    else:
        # 1. Config Comparison Table
        html_parts.append("<div class='card'><h2>1. Configuration Comparison</h2>")
        notice_style = (
            "background: #fffbeb; border: 1px solid #fef3c7; color: #92400e; "
            "padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 13px;"
        )
        html_parts.append(
            f"<div style='{notice_style}'>"
            "<strong>Dev Set Notice:</strong> synthetic template questions (100% contain the gold heading path); "
            "not representative of real users. Recall@5 removed from headline results; "
            "Answer-Bearing Hit@5, MRR, nDCG@5, and Status Accuracy are prioritized."
            "</div>"
        )
        html_parts.append(
            "<table><thead><tr>"
            "<th>Run ID</th><th>Mode</th><th>Prompt</th><th>Answer-Bearing Hit@5</th>"
            "<th>MRR (95% CI)</th><th>nDCG@5 (95% CI)</th><th>Status Acc</th>"
            "<th>Latency p50 / p95</th>"
            "</tr></thead><tbody>"
        )
        for r in reports:
            cfg = r.get("config", {})
            r_over = r.get("retrieval_overall", {})
            abh = r_over.get("answer_bearing_hit") or r_over.get("recall_at_5", {})
            mrr = r_over.get("mrr", {})
            ndcg = r_over.get("ndcg_at_5", {})
            ans_over = r.get("answer_overall") or {}
            st_acc = ans_over.get("status_accuracy", {}).get("mean", 0.0)

            abh_ci = f"[{abh.get('ci_95_low', 0.0):.3f}, {abh.get('ci_95_high', 0.0):.3f}]"
            abh_str = f"{abh.get('mean', 0.0):.3f} <span class='ci'>{abh_ci}</span>"
            mrr_ci = f"[{mrr.get('ci_95_low', 0.0):.3f}, {mrr.get('ci_95_high', 0.0):.3f}]"
            mrr_str = f"{mrr.get('mean', 0.0):.3f} <span class='ci'>{mrr_ci}</span>"
            ndcg_ci = f"[{ndcg.get('ci_95_low', 0.0):.3f}, {ndcg.get('ci_95_high', 0.0):.3f}]"
            ndcg_str = f"{ndcg.get('mean', 0.0):.3f} <span class='ci'>{ndcg_ci}</span>"
            html_parts.append(
                f"<tr>"
                f"<td><strong>{r.get('run_id')}</strong></td>"
                f"<td><span class='code-badge'>{cfg.get('mode', 'unknown')}</span></td>"
                f"<td>{cfg.get('prompt_version', 'v1')}</td>"
                f"<td>{abh_str}</td>"
                f"<td>{mrr_str}</td>"
                f"<td>{ndcg_str}</td>"
                f"<td>{st_acc:.3f}</td>"
                f"<td>{r.get('latency_p50_ms', 0)}ms / {r.get('latency_p95_ms', 0)}ms</td>"
                f"</tr>"
            )
        html_parts.append("</tbody></table></div>")

        # 2. Per-Language Breakdown of Latest Run
        latest = reports[-1]
        html_parts.append(f"<div class='card'><h2>2. Per-Language Performance (Run: {latest.get('run_id')})</h2>")
        html_parts.append(
            "<table><thead><tr>"
            "<th>Language</th><th>Recall@5</th><th>MRR</th><th>nDCG@5</th><th>Status Accuracy</th>"
            "</tr></thead><tbody>"
        )
        r_by_lang = latest.get("retrieval_by_language", {})
        a_by_lang = latest.get("answer_by_language", {})
        all_langs = sorted(set(list(r_by_lang.keys()) + list(a_by_lang.keys())))
        for lang in all_langs:
            rl = r_by_lang.get(lang, {})
            al = a_by_lang.get(lang, {})
            r5_m = rl.get("recall_at_5", {}).get("mean", 0.0)
            mrr_m = rl.get("mrr", {}).get("mean", 0.0)
            ndcg_m = rl.get("ndcg_at_5", {}).get("mean", 0.0)
            st_m = al.get("status_accuracy", {}).get("mean", 0.0)

            html_parts.append(
                f"<tr>"
                f"<td><strong>{lang.upper()}</strong></td>"
                f"<td>{r5_m:.3f}</td>"
                f"<td>{mrr_m:.3f}</td>"
                f"<td>{ndcg_m:.3f}</td>"
                f"<td>{st_m:.3f}</td>"
                f"</tr>"
            )
        html_parts.append("</tbody></table></div>")

        # 3. Error Analysis Table
        worst = latest.get("worst_cases", [])
        html_parts.append(
            f"<div class='card'><h2>3. Error Analysis: Worst Cases ({len(worst)} flagged)</h2>"
        )
        if worst:
            html_parts.append(
                "<table><thead><tr>"
                "<th>Case ID</th><th>Lang</th><th>Reason Code</th><th>Question</th><th>Details</th>"
                "</tr></thead><tbody>"
            )
            for err in worst[:15]:
                html_parts.append(
                    f"<tr>"
                    f"<td><code>{err.get('case_id')}</code></td>"
                    f"<td>{err.get('language')}</td>"
                    f"<td><span class='badge-error'>{err.get('reason_code')}</span></td>"
                    f"<td>{err.get('question')}</td>"
                    f"<td>{err.get('details')}</td>"
                    f"</tr>"
                )
            html_parts.append("</tbody></table>")
        else:
            html_parts.append("<p>No errors recorded in the latest run.</p>")
        html_parts.append("</div>")

    html_parts.extend(["</body>", "</html>"])

    with open(out_file, "w", encoding="utf-8") as out_fp:
        out_fp.write("\n".join(html_parts))
    logger.info("Generated static HTML evaluation report at %s", out_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Float RAG Static HTML Report Generator")
    parser.add_argument("--reports-dir", type=str, default="evals/reports", help="Directory of report JSONs")
    parser.add_argument(
        "--output",
        type=str,
        default="evals/reports/index.html",
        help="Target HTML file path",
    )
    args = parser.parse_args()
    generate_html_report(args.reports_dir, args.output)
    print(f"HTML report generated at: {args.output}")


if __name__ == "__main__":
    main()
