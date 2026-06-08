#!/usr/bin/env python3
"""
scripts/setup/setup_tbench.py — Install T-Bench dependencies.

What this does:
  1. Creates / reuses conda env 'agentic' with Python 3.10+
  2. Installs T-Bench Python packages (FastAPI, uvicorn, httpx, pytest, ...)
  3. No post-install data download required (T-Bench uses a mock REST server)

Usage:
  python3 scripts/setup/setup_tbench.py [--dry-run]
  # All extra flags are forwarded to scripts/setup.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETUP_PY = REPO_ROOT / "scripts" / "setup.py"


def main() -> None:
    extra = sys.argv[1:]
    cmd = [sys.executable, str(SETUP_PY), "--benchmarks", "tbench",
           "--skip-post-install", *extra]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
