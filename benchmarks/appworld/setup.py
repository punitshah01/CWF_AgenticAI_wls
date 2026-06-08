#!/usr/bin/env python3
"""
benchmarks/appworld/setup.py — Install AppWorld dependencies on CWF.

What this does:
  1. Installs git-lfs and OpenSSL dev headers
  2. Creates / reuses conda env 'agentic' (Python 3.11+ — hard requirement)
  3. Installs AppWorld and all dependencies
  4. Runs: appworld install  (~2-3 min, unpacks encrypted bundles)
  5. Runs: appworld download data
  6. Runs: appworld verify tests

Usage:
  python3 benchmarks/appworld/setup.py
  python3 benchmarks/appworld/setup.py --dry-run
  python3 benchmarks/appworld/setup.py --skip-post-install
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    extra = sys.argv[1:]
    # AppWorld hard-requires Python 3.11
    if "--python-version" not in str(extra):
        extra = ["--python-version", "3.11"] + list(extra)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "setup.py"),
        "--benchmarks", "appworld",
        *extra,
    ]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
