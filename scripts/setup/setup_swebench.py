#!/usr/bin/env python3
"""
scripts/setup/setup_swebench.py — Install SWE-bench dependencies.

What this does:
  1. Installs Docker CE (needed for per-task eval containers)
  2. Creates / reuses conda env 'agentic' with Python 3.10+
  3. Installs all SWE-bench Python packages
  4. Clones github.com/SWE-bench/SWE-bench and runs pip install -e .
  5. Validates with gold-patch on 1 task (sympy__sympy-20590)

Usage:
  python3 scripts/setup/setup_swebench.py [--dry-run] [--skip-post-install]
  # All extra flags are forwarded to scripts/setup.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETUP_PY = REPO_ROOT / "scripts" / "setup.py"


def main() -> None:
    extra = sys.argv[1:]
    cmd = [sys.executable, str(SETUP_PY), "--benchmarks", "swebench", *extra]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
