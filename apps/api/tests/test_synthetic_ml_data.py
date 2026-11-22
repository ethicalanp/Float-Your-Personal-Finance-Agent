import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from app.services.borrow_features import FEATURE_COLUMNS
from scripts.generate_synthetic_ml_data import generate_synthetic_datasets
from scripts.train_synthetic_borrow_demo import _read_dataset


def test_synthetic_datasets_are_bounded_marked_and_not_training_compatible(tmp_path: Path) -> None:
    paths = generate_synthetic_datasets(tmp_path, row_count=100, seed=7)

    with paths["borrow"].open(encoding="utf-8", newline="") as file:
        borrow_reader = csv.DictReader(file)
        borrow_rows = list(borrow_reader)
    with paths["scam"].open(encoding="utf-8", newline="") as file:
        scam_reader = csv.DictReader(file)
        scam_rows = list(scam_reader)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert len(borrow_rows) == len(scam_rows) == 100
    assert set(FEATURE_COLUMNS).issubset(borrow_reader.fieldnames or [])
    assert "synthetic_target_default" in borrow_reader.fieldnames
    assert "target_default" not in borrow_reader.fieldnames
    assert "synthetic_is_scam" in scam_reader.fieldnames
    assert "is_scam" not in scam_reader.fieldnames
    assert "template_group" in scam_reader.fieldnames
    assert {row["lang"] for row in scam_rows} == {"en", "ml", "manglish"}
    assert all(row["text"].startswith("SYNTHETIC TEST ONLY:") for row in scam_rows)
    assert all(
        len({row["synthetic_is_scam"] for row in scam_rows if row["template_group"] == group}) == 1
        for group in {row["template_group"] for row in scam_rows}
    )
    assert len({row["template_group"] for row in scam_rows}) == 24
    assert manifest["dataset_status"] == "synthetic_pipeline_test_only"


def test_synthetic_generator_rejects_invalid_size_and_overwrite(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="between 100 and 500"):
        generate_synthetic_datasets(tmp_path, row_count=99)

    generate_synthetic_datasets(tmp_path, row_count=100)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        generate_synthetic_datasets(tmp_path, row_count=100)


def test_synthetic_borrow_reader_keeps_labels_aligned_when_sorting_dates(tmp_path: Path) -> None:
    paths = generate_synthetic_datasets(tmp_path, row_count=120)
    original = pd.read_csv(paths["borrow"])
    expected_labels = dict(zip(original["as_of_date"], original["synthetic_target_default"], strict=True))
    original.sample(frac=1, random_state=17).to_csv(paths["borrow"], index=False)

    data, labels, _ = _read_dataset(tmp_path)

    assert data["as_of_date"].is_monotonic_increasing
    assert labels.tolist() == [expected_labels[value.isoformat()] for value in data["as_of_date"]]
