#!/usr/bin/env python3
"""
benchmarks/appworld/setup.py - Self-contained AppWorld setup for CWF.

Steps:
  1. Create / reuse conda env (Python 3.11+ -- hard requirement)
  2. Install AppWorld Python packages (idempotent -- skips if already satisfied)
  3. Run: appworld install   (~2-3 min, unpacks encrypted bundles)
  4. Run: appworld download data
  5. Run: appworld verify tests

Usage:
  python3 benchmarks/appworld/setup.py
  python3 benchmarks/appworld/setup.py --dry-run
  python3 benchmarks/appworld/setup.py --skip-post-install
  python3 benchmarks/appworld/setup.py --conda-env myenv
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

require_python_version((3, 11), benchmark_name="AppWorld")

CONDA_ENV = "agentic"

PACKAGES: List[str] = [
    "appworld",
    "fastapi>=0.110",
    "fastapi-login>=1.10.2",
    "sqlmodel>=0.0.19",
    "pydantic>=2.12.0",
    "sqlalchemy-utils>=0.41.1",
    "pendulum>=3.0.0",
    "freezegun>=1.5.0,<=1.5.1",
    "uvicorn>=0.27",
    "ipython>=8.18.0",
    "typer>=0.16.0",
    "text2num>=0.3.0",
    "orjson>=3.10.12",
    "pydantic-extra-types[pendulum]>=2.8.0",
    "requests>=2.28.0",
    "inflection>=0.5.1",
    "email-validator>=2.0.0",
    "polyfactory>=2.15.0",
    "faker>=18.0.0",
    "xxhash>=3.0.0",
    "munch>=4.0.0",
    "rich>=13.0.0",
    "tqdm>=4.60.0",
    "python-dotenv>=1.0.1",
    "cryptography>=44.0.0",
    "python-multipart>=0.0.5",
    "httpx>=0.20.0",
    "libcst>=1.2.0",
    "typing-extensions>=4.12.2",
    "pyyaml>=6.0.1",
    "psutil>=5.9.0",
    "jsonref>=1.1.0",
    "filelock>=3.1.0",
    "uvloop>=0.21.0",
]

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Setup steps (workload-specific: package list + appworld CLI post-install)
# ---------------------------------------------------------------------------

def setup_conda_env(conda_env: str, dry_run: bool) -> None:
    ensure_conda_env(conda_env, "3.11", dry_run, banner_title="Step 1: Conda Environment (Python 3.11)")

def install_packages(conda_env: str, dry_run: bool) -> None:
    banner("Step 2: AppWorld Python Packages")
    pip = get_conda_pip(conda_env)
    run(f"{pip} install --upgrade pip setuptools wheel", dry_run=dry_run)
    log(f"Installing {len(PACKAGES)} packages (skipping already-satisfied)...", "info")
    pip_install(pip, PACKAGES, dry_run)
    log("Python packages done", "ok")

def post_install(conda_env: str, dry_run: bool) -> None:
    banner("Step 3: AppWorld Post-Install")
    log("appworld install  (~2-3 min)", "info")
    run(f"conda run -n {conda_env} appworld install", dry_run=dry_run)
    log("appworld download data", "info")
    run(f"conda run -n {conda_env} appworld download data", dry_run=dry_run)
    log("appworld verify tests", "info")
    run(f"conda run -n {conda_env} appworld verify tests", dry_run=dry_run)
    log("AppWorld post-install done", "ok")

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AppWorld setup for CWF",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--dry-run",          action="store_true")
    p.add_argument("--skip-post-install", action="store_true",
                   help="Skip appworld install/download/verify steps")
    p.add_argument("--conda-env",        default=CONDA_ENV)
    return p.parse_args()

def main() -> None:
    args = parse_args()
    banner("AppWorld Setup for CWF")
    setup_conda_env(args.conda_env, args.dry_run)
    install_packages(args.conda_env, args.dry_run)
    if not args.skip_post_install:
        post_install(args.conda_env, args.dry_run)
    log("AppWorld setup complete.", "ok")
    if not args.dry_run:
        setup_marker = Path(__file__).resolve().parent / ".setup_complete"
        write_setup_marker(setup_marker, "AppWorld", [f"conda_env: {args.conda_env}"])
    print(f"\n  Next: conda activate {args.conda_env}")
    print( "        python3 benchmarks/appworld/run.py")
    print("\n[SUCCESS] AppWorld setup complete")
    sys.exit(0)

if __name__ == "__main__":
    main()
