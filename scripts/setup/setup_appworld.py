#!/usr/bin/env python3
"""
scripts/setup/setup_appworld.py — Install AppWorld dependencies.

What this does:
  1. Installs git-lfs and OpenSSL dev headers
  2. Creates / reuses conda env 'agentic' with Python 3.11+ (hard requirement)
  3. Installs all AppWorld Python packages via pip
  4. Runs: appworld install  (unpacks encrypted data bundles, ~2-3 min)
  5. Runs: appworld download data
  6. Runs: appworld verify tests

Usage:
  python3 scripts/setup/setup_appworld.py [--dry-run] [--skip-post-install]
  # All extra flags are forwarded to scripts/setup.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETUP_PY = REPO_ROOT / "scripts" / "setup.py"


def main() -> None:
    extra = sys.argv[1:]
    # AppWorld hard-requires Python 3.11; enforce it
    if "--python-version" not in str(extra):
        extra = ["--python-version", "3.11"] + list(extra)
    cmd = [sys.executable, str(SETUP_PY), "--benchmarks", "appworld", *extra]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
