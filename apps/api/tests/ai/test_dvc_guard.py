"""Guard test to ensure data/ and evals/data/ files are never tracked by Git.

Only .dvc pointer files, manifests (manifest.sha256), and test fixtures under tests/fixtures
are permitted to be tracked by Git.
"""

import subprocess
from pathlib import Path


def test_no_data_tracked_by_git():
    # Run git ls-files on data/ and evals/data/
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "ls-files", "data/", "evals/data/"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    # Filter out permitted exceptions: *.dvc, manifest.sha256
    violating_files = []
    for f in tracked_files:
        p = Path(f)
        if p.suffix == ".dvc":
            continue
        if p.name == "manifest.sha256":
            continue
        violating_files.append(f)

    assert not violating_files, (
        "Data files must NEVER be tracked directly by Git (use DVC instead):\n"
        + "\n".join(violating_files)
    )
