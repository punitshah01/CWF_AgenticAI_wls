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
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

if sys.version_info < (3, 10):
    sys.exit(f"[ERROR] Python 3.10+ required. Current: {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
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

def setup_conda_env(conda_env: str, python_version: str, dry_run: bool) -> None:
    banner("Step 1: Conda Environment")
    if not shutil.which("conda"):
        log("conda not found -- run scripts/setup.py first", "error")
        sys.exit(1)
    result = subprocess.run("conda env list", shell=True, capture_output=True, text=True)
    if not dry_run and conda_env in (result.stdout or ""):
        log(f"Conda env '{conda_env}' already exists.", "ok")
    else:
        run(f"conda create -y -n {conda_env} python={python_version}", dry_run=dry_run)
        log(f"Conda env '{conda_env}' created", "ok")

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
    print(f"\n  Next: conda activate {args.conda_env}")
    print( "        python3 benchmarks/t-bench/run.py")

if __name__ == "__main__":
    main()
