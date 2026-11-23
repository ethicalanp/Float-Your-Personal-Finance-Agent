from pathlib import Path
from typing import Any

import yaml

from app.ai.rag.models import Manifest, ManifestSource


class ManifestValidationError(Exception):
    """Raised when manifest.yaml fails schema validation."""

    pass


def load_manifest(path: Path | str) -> Manifest:
    """Load and validate manifest.yaml using Pydantic schema."""
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    try:
        with open(manifest_path, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except Exception as e:
        raise ManifestValidationError(f"Failed to parse YAML from {manifest_path}: {e}") from e

    if not isinstance(raw_data, dict):
        raise ManifestValidationError(f"Manifest root must be a YAML dictionary, got {type(raw_data)}")

    raw_sources: Any = raw_data.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ManifestValidationError(f"'sources' key in manifest must be a list, got {type(raw_sources)}")

    sources: list[ManifestSource] = []
    seen_ids: set[str] = set()

    for item in raw_sources:
        try:
            source = ManifestSource(**item)
            if source.id in seen_ids:
                raise ManifestValidationError(f"Duplicate source ID in manifest: '{source.id}'")
            seen_ids.add(source.id)
            sources.append(source)
        except Exception as e:
            raise ManifestValidationError(f"Invalid manifest source item {item}: {e}") from e

    return Manifest(sources=sources)
