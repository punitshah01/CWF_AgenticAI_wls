#!/usr/bin/env python3
"""
benchmarks/swebench/setup.py — Install SWE-bench dependencies on CWF.

What this does:
  1. Installs Docker CE (required for per-task eval containers)
  2. Creates / reuses conda env 'agentic' (Python 3.10+)
  3. Installs all SWE-bench Python packages
  4. Clones github.com/SWE-bench/SWE-bench and pip install -e .
  5. Validates with gold-patch on 1 task (sympy__sympy-20590)

Usage:
  python3 benchmarks/swebench/setup.py
  python3 benchmarks/swebench/setup.py --dry-run
  python3 benchmarks/swebench/setup.py --skip-post-install
  python3 benchmarks/swebench/setup.py --registry localhost:5000
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    extra = sys.argv[1:]
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "setup.py"),
        "--benchmarks", "swebench",
        *extra,
    ]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
