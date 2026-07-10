#!/usr/bin/env python3
"""
benchmarks/swe-bench/setup.py - Self-contained SWE-bench setup for CWF.

Steps:
  1. Create / reuse conda env (Python 3.10+)
  2. Install SWE-bench Python packages (idempotent -- skips if already satisfied)
  3. Clone github.com/SWE-bench/SWE-bench and pip install -e .
  4. Optional: validate with gold-patch on 1 task

Usage:
  python3 benchmarks/swe-bench/setup.py
  python3 benchmarks/swe-bench/setup.py --dry-run
  python3 benchmarks/swe-bench/setup.py --skip-validate
  python3 benchmarks/swe-bench/setup.py --conda-env myenv
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

WORKDIR   = Path.home() / "cwf_agentic" / "swebench"
CONDA_ENV = "agentic"

PACKAGES: List[str] = [
    "swebench",
    "swe-agent",
    "beautifulsoup4",
    "chardet",
    "datasets>=2.14",
    "docker>=6.0",
    "ghapi",
    "GitPython",
    "modal",
    "python-dotenv",
    "requests>=2.28.0",
    "rich>=13.0",
    "tenacity",
    "tqdm>=4.60",
    "unidiff",
    "protobuf",
    "sentencepiece",
    "tiktoken",
    "transformers>=4.35.2",
    "openai>=1.0",
    "anthropic",
    "jedi",
    "pytest>=7.0",
    "pytest-cov",
]

# ---------------------------------------------------------------------------
# Setup steps (workload-specific: package list, repo clone, gold-patch check)
# ---------------------------------------------------------------------------

def setup_conda_env(conda_env: str, python_version: str, dry_run: bool) -> None:
    ensure_conda_env(conda_env, python_version, dry_run, banner_title="Step 1: Conda Environment")

def install_packages(conda_env: str, dry_run: bool) -> None:
    banner("Step 2: SWE-bench Python Packages")
    pip = get_conda_pip(conda_env)
    run(f"{pip} install --upgrade pip setuptools wheel", dry_run=dry_run)
    log(f"Installing {len(PACKAGES)} packages (skipping already-satisfied)...", "info")
    pip_install(pip, PACKAGES, dry_run)
    log("Python packages done", "ok")

def clone_and_install(conda_env: str, dry_run: bool) -> None:
    banner("Step 3: Clone SWE-bench Repository")
    if not dry_run and WORKDIR.exists() and (WORKDIR / "setup.py").exists():
        log(f"SWE-bench already cloned at {WORKDIR}", "ok")
    else:
        WORKDIR.parent.mkdir(parents=True, exist_ok=True)
        run(f"git clone https://github.com/SWE-bench/SWE-bench.git {WORKDIR}", dry_run=dry_run)
    pip = get_conda_pip(conda_env)
    run(f"{pip} install --quiet -e {WORKDIR}", dry_run=dry_run)
    log("SWE-bench installed in editable mode", "ok")

def validate(conda_env: str, dry_run: bool) -> None:
    banner("Step 4: Gold-Patch Validation (1 task)")
    run(
        f"conda run -n {conda_env} python -m swebench.harness.run_evaluation "
        f"--predictions_path gold --max_workers 1 "
        f"--instance_ids sympy__sympy-20590 --run_id validate-gold",
        dry_run=dry_run,
    )
    log("Validation done", "ok")

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SWE-bench setup for CWF",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--dry-run",        action="store_true")
    p.add_argument("--skip-validate",  action="store_true", help="Skip gold-patch validation")
    p.add_argument("--conda-env",      default=CONDA_ENV)
    p.add_argument("--python-version", default="3.10")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    banner("SWE-bench Setup for CWF")
    setup_conda_env(args.conda_env, args.python_version, args.dry_run)
    install_packages(args.conda_env, args.dry_run)
    clone_and_install(args.conda_env, args.dry_run)
    if not args.skip_validate:
        validate(args.conda_env, args.dry_run)
    log("SWE-bench setup complete.", "ok")
    if not args.dry_run:
        setup_marker = Path(__file__).resolve().parent / ".setup_complete"
        write_setup_marker(setup_marker, "SWE-bench", [f"conda_env: {args.conda_env}"])
    print(f"\n  Next: conda activate {args.conda_env}")
    print( "        python3 benchmarks/swe-bench/run.py")
    print("\n[SUCCESS] SWE-bench setup complete")
    sys.exit(0)

if __name__ == "__main__":
    main()
