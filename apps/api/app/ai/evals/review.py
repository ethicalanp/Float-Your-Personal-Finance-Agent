import csv
import json
import random
from pathlib import Path
from typing import Sequence

from app.ai.evals.models import CaseSplit, RAGCaseStatus, RAGEvalCase, RAGReviewAction

CSV_FIELDNAMES = [
    "id",
    "language",
    "type",
    "question",
    "reference_answer",
    "gold_chunk_id",
    "required_facts",
    "status",
    "review_action",
    "review_notes",
    "split",
    "needs_native_review",
]


def export_drafts_to_csv(cases: Sequence[RAGEvalCase], csv_path: Path | str) -> None:
    """Export draft or reviewed eval cases to CSV for human review."""
    target = Path(csv_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for c in cases:
            writer.writerow(
                {
                    "id": c.id,
                    "language": c.language,
                    "type": c.type,
                    "question": c.question,
                    "reference_answer": c.reference_answer,
                    "gold_chunk_id": c.gold_chunk_id or "",
                    "required_facts": json.dumps(c.required_facts, ensure_ascii=False),
                    "status": c.status,
                    "review_action": c.review_action or "",
                    "review_notes": c.review_notes or "",
                    "split": c.split,
                    "needs_native_review": "yes" if c.needs_native_review else "no",
                }
            )


def import_reviewed_from_csv(csv_path: Path | str, promote_drafts: bool = False) -> list[RAGEvalCase]:
    """Import human reviewed cases from CSV (BOM-safe).

    Cases marked with review_action 'approve' or edited are promoted to status='reviewed'.
    Cases marked with 'reject' are set to status='rejected'.
    If promote_drafts is True, un-rejected draft cases are also treated as status='reviewed'.
    Cases in Malayalam and Manglish are flagged needs_native_review=True.
    """
    source = Path(csv_path)
    if not source.exists():
        raise FileNotFoundError(f"Review CSV not found: {source}")

    cases: list[RAGEvalCase] = []
    with open(source, mode="r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_facts = row.get("required_facts", "[]")
            try:
                required_facts = json.loads(raw_facts) if raw_facts else []
                if not isinstance(required_facts, list):
                    required_facts = [str(required_facts)]
            except Exception:
                required_facts = [f.strip() for f in raw_facts.split(",") if f.strip()]

            action_raw = (row.get("review_action") or "").strip().lower()
            review_action: RAGReviewAction | None = None
            if action_raw in ("approve", "approved"):
                review_action = "approve"
            elif action_raw in ("edit", "edited"):
                review_action = "edit"
            elif action_raw in ("reject", "rejected"):
                review_action = "reject"

            # Determine status based on review action, promote_drafts flag, or explicit status
            existing_status = (row.get("status") or "draft").strip().lower()
            if review_action in ("approve", "edit"):
                status: RAGCaseStatus = "reviewed"
            elif review_action == "reject":
                status = "rejected"
            elif promote_drafts and existing_status == "draft":
                status = "reviewed"
            elif existing_status in ("reviewed", "rejected", "draft"):
                status = existing_status  # type: ignore[assignment]
            else:
                status = "draft"

            lang = (row.get("language") or "en").strip().lower()
            case_type = (row.get("type") or "answerable").strip().lower()
            split_val = (row.get("split") or "dev").strip().lower()

            needs_native = lang in ("ml", "manglish")

            case = RAGEvalCase(
                id=row["id"].strip(),
                language=lang if lang in ("en", "ml", "manglish") else "en",  # type: ignore[arg-type]
                type=case_type  # type: ignore[arg-type]
                if case_type in ("answerable", "unanswerable", "refusal_expected", "adversarial")
                else "answerable",
                question=row.get("question", "").strip(),
                reference_answer=row.get("reference_answer", "").strip(),
                gold_chunk_id=row.get("gold_chunk_id", "").strip() or None,
                required_facts=required_facts,
                status=status,
                review_action=review_action,
                review_notes=(row.get("review_notes") or "").strip(),
                split="test" if split_val == "test" else "dev",
                needs_native_review=needs_native,
            )
            cases.append(case)

    return cases


def split_reviewed_cases(
    cases: Sequence[RAGEvalCase],
    dev_ratio: float = 0.6,
    seed: int = 42,
) -> list[RAGEvalCase]:
    """Deterministically split reviewed cases into dev and test partitions using fixed seed.

    Stratifies by (language, type). Only operates on cases with status == 'reviewed'.
    """
    groups: dict[tuple[str, str], list[int]] = {}

    for idx, c in enumerate(cases):
        if c.status == "reviewed":
            key = (c.language, c.type)
            groups.setdefault(key, []).append(idx)

    rng = random.Random(seed)
    updated_cases = [c.model_copy() for c in cases]

    for _key, indices in groups.items():
        shuffled = list(indices)
        rng.shuffle(shuffled)
        if len(shuffled) > 1:
            n_dev = max(1, min(len(shuffled) - 1, int(round(len(shuffled) * dev_ratio))))
        else:
            n_dev = 1 if rng.random() < dev_ratio else 0
        dev_set = set(shuffled[:n_dev])

        for idx in shuffled:
            split: CaseSplit = "dev" if idx in dev_set else "test"
            updated_cases[idx].split = split

    return updated_cases


def save_cases_jsonl(cases: Sequence[RAGEvalCase], path: Path | str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(c.model_dump_json() + "\n")


def load_cases_jsonl(path: Path | str, split: str | None = None, only_reviewed: bool = True) -> list[RAGEvalCase]:
    source = Path(path)
    if not source.exists():
        return []
    cases: list[RAGEvalCase] = []
    with open(source, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            case = RAGEvalCase(**item)
            if only_reviewed and case.status != "reviewed":
                continue
            if split and case.split != split:
                continue
            cases.append(case)
    return cases
