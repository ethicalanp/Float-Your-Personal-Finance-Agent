"""Runner wrapper for Grounded RAG answer smoke test."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    api_dir = Path(__file__).parent.parent / "apps" / "api"
    script = api_dir / "scripts" / "answer_smoke.py"
    venv_py = Path(__file__).parent.parent / "venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable

    os.environ["PYTHONPATH"] = str(api_dir)
    res = subprocess.run([py, str(script)], cwd=str(api_dir))
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
