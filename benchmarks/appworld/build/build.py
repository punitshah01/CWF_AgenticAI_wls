#!/usr/bin/env python3
"""
benchmarks/appworld/build/build.py — Install AppWorld Python dependencies.

Usage:
  python3 benchmarks/appworld/build/build.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> None:
    reqs = SCRIPT_DIR / "requirements.txt"
    if not reqs.is_file():
        print(f"[ERROR] requirements.txt not found at {reqs}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Installing {reqs} ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(reqs)],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] pip install failed (exit {e.returncode})", file=sys.stderr)
        sys.exit(1)

    print("[ OK ] AppWorld dependencies installed")


if __name__ == "__main__":
    main()
