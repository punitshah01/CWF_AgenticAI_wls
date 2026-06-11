#!/usr/bin/env python3
"""
setup/setup_venv.py — Create a Python virtual environment and install root requirements.

Usage:
  python3 setup/setup_venv.py
  python3 setup/setup_venv.py --python python3.11   # explicit Python interpreter
  python3 setup/setup_venv.py --venv-dir /opt/cwf-venv
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a Python virtual environment for CWF agentic workloads.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--python",
        default="python3",
        metavar="BIN",
        help="Python interpreter to use (e.g. python3.11)",
    )
    parser.add_argument(
        "--venv-dir",
        default=str(REPO_ROOT / ".venv"),
        metavar="DIR",
        help="Directory to create the virtual environment in",
    )
    args = parser.parse_args()

    python_bin = args.python
    venv_dir = Path(args.venv_dir)

    print("=== CWF Python venv setup ===")
    print(f"Python  : {python_bin}")
    print(f"Venv dir: {venv_dir}")
    print(f"Repo    : {REPO_ROOT}")
    print()

    # Verify the Python interpreter exists
    result = subprocess.run(
        [python_bin, "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ERROR] Python interpreter not found: {python_bin}", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] Using {result.stdout.strip()}")

    # Create venv if it does not already exist
    if venv_dir.is_dir():
        print(f"[INFO] Venv already exists at {venv_dir} — skipping creation")
    else:
        print("[INFO] Creating virtual environment ...")
        try:
            subprocess.run(
                [python_bin, "-m", "venv", str(venv_dir)],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to create venv: {e}", file=sys.stderr)
            sys.exit(1)
        print("[ OK ] Venv created")

    pip = str(venv_dir / "bin" / "pip")

    # Upgrade pip / setuptools / wheel (idempotent)
    print("[INFO] Upgrading pip/setuptools/wheel ...")
    try:
        subprocess.run(
            [pip, "install", "--quiet", "--upgrade", "pip", "setuptools", "wheel"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] pip upgrade failed (exit {e.returncode})", file=sys.stderr)
        sys.exit(1)

    # Install root requirements.txt if present
    root_reqs = REPO_ROOT / "requirements.txt"
    if root_reqs.is_file():
        print(f"[INFO] Installing {root_reqs} ...")
        try:
            subprocess.run(
                [pip, "install", "--quiet", "-r", str(root_reqs)],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Root requirements install failed (exit {e.returncode})", file=sys.stderr)
            sys.exit(1)
        print("[ OK ] Root requirements installed")
    else:
        print("[WARN] No root requirements.txt found — skipping")

    print()
    print("[ OK ] Venv ready. To activate:")
    print(f"       source {venv_dir}/bin/activate")


if __name__ == "__main__":
    main()
