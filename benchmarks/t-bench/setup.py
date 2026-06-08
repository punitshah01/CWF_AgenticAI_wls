#!/usr/bin/env python3
"""
benchmarks/t-bench/setup.py — Install T-Bench dependencies on CWF.

What this does:
  1. Creates / reuses conda env 'agentic' (Python 3.10+)
  2. Installs T-Bench Python packages (FastAPI, uvicorn, httpx, pytest, ...)
  3. No post-install data download required (uses a mock REST server)

Usage:
  python3 benchmarks/t-bench/setup.py
  python3 benchmarks/t-bench/setup.py --dry-run
"""

import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit(f"[ERROR] Python 3.10+ required. Current: {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    extra = sys.argv[1:]
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "setup.py"),
        "--benchmarks", "tbench",
        "--skip-post-install",
        *extra,
    ]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
