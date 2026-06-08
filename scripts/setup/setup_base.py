#!/usr/bin/env python3
"""
scripts/setup/setup_base.py — Install base system dependencies for all benchmarks.

Installs: git, curl, wget, build-essential/gcc, cmake, numactl, hwloc,
          msr-tools, python3-pip, python3-dev, conda/Miniconda.

Usage:
  python3 scripts/setup/setup_base.py [--dry-run] [--skip-system]
  # All extra flags are forwarded to scripts/setup.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETUP_PY = REPO_ROOT / "scripts" / "setup.py"


def main() -> None:
    extra = sys.argv[1:]
    cmd = [
        sys.executable, str(SETUP_PY),
        "--benchmarks", "swebench", "webarena", "osworld", "appworld", "tbench",
        "--skip-python",         # base install — Python packages handled per-benchmark
        "--skip-image-pull",     # no Docker images needed for base
        "--skip-post-install",
        *extra,
    ]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
