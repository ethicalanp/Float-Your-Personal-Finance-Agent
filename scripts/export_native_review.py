import csv
import json
from pathlib import Path

DATASETS_DIR = Path("evals/datasets")
OUTPUT_CSV = Path("evals/review/needs_native_review.csv")
OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

csv_rows = []
suite_stats = {}

for jsonl_file in sorted(DATASETS_DIR.glob("*.jsonl")):
    dataset_name = jsonl_file.stem
    suite_stats[dataset_name] = {
        "total": 0,
        "human_reviewed": 0,
        "draft": 0,
        "en": 0,
        "ml": 0,
        "manglish": 0,
        "needs_native_review": 0,
    }
    updated_lines = []

    with open(jsonl_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            suite_stats[dataset_name]["total"] += 1

            status = case.get("review_status", case.get("status", "human_reviewed"))
            if status in ("human_reviewed", "reviewed"):
                suite_stats[dataset_name]["human_reviewed"] += 1
            else:
                suite_stats[dataset_name]["draft"] += 1

            lang = case.get("language", "en")
            if lang in suite_stats[dataset_name]:
                suite_stats[dataset_name][lang] += 1

            # Mark all Malayalam and Manglish cases as needing native review
            if lang in ("ml", "manglish"):
                case["needs_native_review"] = True

            needs_review = case.get("needs_native_review", False)
            if needs_review:
                suite_stats[dataset_name]["needs_native_review"] += 1
                q_text = case.get("inputs", {}).get("question") or case.get("question") or case.get("inputs", {}).get("text") or ""
                expected = (
                    case.get("expected_route")
                    or case.get("type")
                    or case.get("expected_chunk_ids")
                    or case.get("expected_facts")
                    or ""
                )
                csv_rows.append({
                    "dataset": dataset_name,
                    "case_id": case.get("id", ""),
                    "language": lang,
                    "review_status": status,
                    "needs_native_review": "True",
                    "question_or_input": str(q_text).replace("\n", " "),
                    "expected_outcome": str(expected).replace("\n", " ")[:120],
                    "notes": case.get("notes", "Requires native speaker grammar, terminology, and dialect check"),
                })

            updated_lines.append(json.dumps(case, ensure_ascii=False))

    # Write back updated jsonl
    with open(jsonl_file, "w", encoding="utf-8") as f:
        for u in updated_lines:
            f.write(u + "\n")

# Write CSV
fieldnames = [
    "dataset",
    "case_id",
    "language",
    "review_status",
    "needs_native_review",
    "question_or_input",
    "expected_outcome",
    "notes",
]
with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in csv_rows:
        writer.writerow(row)

print("=== DATASET STATISTICS ===")
for ds, stats in suite_stats.items():
    print(f"Dataset '{ds}': total={stats['total']}, human_reviewed={stats['human_reviewed']}, draft={stats['draft']}, en={stats['en']}, ml={stats['ml']}, manglish={stats['manglish']}, needs_native_review={stats['needs_native_review']}")

print(f"\nTotal exported to {OUTPUT_CSV}: {len(csv_rows)} cases")
