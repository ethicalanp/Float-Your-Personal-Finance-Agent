from pathlib import Path

import pytest

from app.ai.rag.manifest import ManifestValidationError, load_manifest
from app.ai.rag.models import Manifest, ManifestSource


def test_manifest_validation_valid(tmp_path: Path) -> None:
    manifest_yaml = """
sources:
  - id: fixture-rbi-valid
    title: "[FIXTURE] RBI Master Direction"
    publisher: "Reserve Bank of India"
    source_url: "https://rbi.org.in/valid-path"
    file_path: "fixtures/rbi.md"
    language: "en"
    doc_type: "circular"
    licence_note: "FIXTURE - Open Public Domain"
    publication_date: 2026-01-10
"""
    m_file = tmp_path / "manifest.yaml"
    m_file.write_text(manifest_yaml, encoding="utf-8")

    manifest = load_manifest(m_file)
    assert len(manifest.sources) == 1
    src = manifest.sources[0]
    assert src.id == "fixture-rbi-valid"
    assert src.publisher == "Reserve Bank of India"
    assert "rbi.org.in" in manifest.domain_allowlist()


def test_manifest_validation_rejects_missing_source_and_path(tmp_path: Path) -> None:
    manifest_yaml = """
sources:
  - id: fixture-invalid
    title: "[FIXTURE] Invalid Source"
    publisher: "Test"
    language: "en"
"""
    m_file = tmp_path / "invalid.yaml"
    m_file.write_text(manifest_yaml, encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="must provide either 'source_url' or 'file_path'"):
        load_manifest(m_file)


def test_manifest_validation_rejects_duplicate_ids(tmp_path: Path) -> None:
    manifest_yaml = """
sources:
  - id: fixture-duplicate
    title: "[FIXTURE] Doc 1"
    publisher: "Test"
    file_path: "doc1.md"
  - id: fixture-duplicate
    title: "[FIXTURE] Doc 2"
    publisher: "Test"
    file_path: "doc2.md"
"""
    m_file = tmp_path / "dup.yaml"
    m_file.write_text(manifest_yaml, encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="Duplicate source ID"):
        load_manifest(m_file)


def test_manifest_domain_allowlist_calculation() -> None:
    manifest = Manifest(
        sources=[
            ManifestSource(
                id="fixture-1",
                title="[FIXTURE] Source 1",
                publisher="Pub 1",
                source_url="https://cybercrime.gov.in/advisories/1",
            ),
            ManifestSource(
                id="fixture-2",
                title="[FIXTURE] Source 2",
                publisher="Pub 2",
                source_url="https://rbi.org.in:443/circular",
            ),
            ManifestSource(
                id="fixture-3",
                title="[FIXTURE] Local Only",
                publisher="Pub 3",
                file_path="local.md",
            ),
        ]
    )

    allowlist = manifest.domain_allowlist()
    assert allowlist == {"cybercrime.gov.in", "rbi.org.in"}
