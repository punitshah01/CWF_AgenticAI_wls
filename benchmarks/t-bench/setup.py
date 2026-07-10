#!/usr/bin/env python3
"""
benchmarks/t-bench/setup.py - Self-contained T-Bench setup for CWF.

Steps:
  1. Create / reuse conda env (Python 3.10+)
  2. Install T-Bench Python packages (idempotent -- skips if already satisfied)

Usage:
  python3 benchmarks/t-bench/setup.py
  python3 benchmarks/t-bench/setup.py --dry-run
  python3 benchmarks/t-bench/setup.py --conda-env myenv
"""

import argparse
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from common.setup_utils import (  # noqa: E402
    banner, ensure_conda_env, get_conda_pip, log, pip_install,
    require_python_version, run, write_setup_marker,
)

require_python_version((3, 10))

CONDA_ENV = "agentic"

PACKAGES: List[str] = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "requests>=2.28.0",
    "jsonschema>=4.19.0",
    "pydantic>=2.12.0",
    "rich>=13.0.0",
    "tqdm>=4.60.0",
    "python-dotenv>=1.0.1",
    "httpx>=0.20.0",
    "pytest>=7.0.0",
]

# ---------------------------------------------------------------------------
# Setup steps (workload-specific: package list + conda env for T-Bench)
# ---------------------------------------------------------------------------

def setup_conda_env(conda_env: str, python_version: str, dry_run: bool) -> None:
    ensure_conda_env(conda_env, python_version, dry_run, banner_title="Step 1: Conda Environment")

def install_packages(conda_env: str, dry_run: bool) -> None:
    banner("Step 2: T-Bench Python Packages")
    pip = get_conda_pip(conda_env)
    run(f"{pip} install --upgrade pip setuptools wheel", dry_run=dry_run)
    log(f"Installing {len(PACKAGES)} packages (skipping already-satisfied)...", "info")
    pip_install(pip, PACKAGES, dry_run)
    log("Python packages done", "ok")

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="T-Bench setup for CWF",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--dry-run",        action="store_true")
    p.add_argument("--conda-env",      default=CONDA_ENV)
    p.add_argument("--python-version", default="3.10")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    banner("T-Bench Setup for CWF")
    setup_conda_env(args.conda_env, args.python_version, args.dry_run)
    install_packages(args.conda_env, args.dry_run)
    log("T-Bench setup complete.", "ok")
    if not args.dry_run:
        setup_marker = Path(__file__).resolve().parent / ".setup_complete"
        write_setup_marker(setup_marker, "T-Bench", [f"conda_env: {args.conda_env}"])
    print(f"\n  Next: conda activate {args.conda_env}")
    print( "        python3 benchmarks/t-bench/run.py")
    print("\n[SUCCESS] T-Bench setup complete")
    sys.exit(0)

if __name__ == "__main__":
    main()
