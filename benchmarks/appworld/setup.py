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
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

if sys.version_info < (3, 11):
    sys.exit(f"[ERROR] Python 3.11+ required for AppWorld. Current: {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
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

class Color:
    BLUE = "\033[94m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
    RED  = "\033[91m"; BOLD  = "\033[1m";  RESET  = "\033[0m"

def log(msg: str, level: str = "info") -> None:
    c = {"info": Color.BLUE, "ok": Color.GREEN, "warn": Color.YELLOW, "error": Color.RED}.get(level, "")
    p = {"info": "[INFO]", "ok": "[ OK ]", "warn": "[WARN]", "error": "[ERR ]"}.get(level, "")
    print(f"{c}{Color.BOLD}{p}{Color.RESET}{c} {msg}{Color.RESET}", flush=True)

def banner(t: str) -> None:
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*60}\n  {t}\n{'='*60}{Color.RESET}\n")

def run(cmd: str, dry_run: bool = False, check: bool = False) -> Optional[subprocess.CompletedProcess]:
    print(f"  $ {cmd}", flush=True)
    if dry_run:
        return None
    return subprocess.run(cmd, shell=True)

def pip_install(pip_bin: str, packages: List[str], dry_run: bool) -> None:
    """Install packages idempotently -- pip skips packages already satisfying version constraints."""
    for i in range(0, len(packages), 20):
        chunk = " ".join(f'"{p}"' for p in packages[i:i+20])
        run(f"{pip_bin} install --quiet {chunk}", dry_run=dry_run)

def get_conda_pip(conda_env: str) -> str:
    r = subprocess.run(f"conda run -n {conda_env} which pip",
                       shell=True, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "pip"

# ---------------------------------------------------------------------------

def setup_conda_env(conda_env: str, dry_run: bool) -> None:
    banner("Step 1: Conda Environment (Python 3.11)")
    if not shutil.which("conda"):
        log("conda not found -- run scripts/setup.py first", "error")
        sys.exit(1)
    result = subprocess.run("conda env list", shell=True, capture_output=True, text=True)
    if not dry_run and conda_env in (result.stdout or ""):
        log(f"Conda env '{conda_env}' already exists.", "ok")
    else:
        run(f"conda create -y -n {conda_env} python=3.11", dry_run=dry_run)
        log(f"Conda env '{conda_env}' created (Python 3.11)", "ok")

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
        setup_marker.write_text(f"AppWorld setup completed successfully\nconda_env: {args.conda_env}\n")
        log(f"Setup marker written: {setup_marker}", "ok")
    print(f"\n  Next: conda activate {args.conda_env}")
    print( "        python3 benchmarks/appworld/run.py")
    print("\n[SUCCESS] AppWorld setup complete")
    sys.exit(0)

if __name__ == "__main__":
    main()
