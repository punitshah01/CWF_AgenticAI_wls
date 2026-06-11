#!/usr/bin/env python3
"""
benchmarks/osworld/build/build.py — Install OSWorld Python dependencies.

Usage:
  python3 benchmarks/osworld/build/build.py
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
    print("[ OK ] pip install complete")

    # Playwright is optional for OSWorld (accessibility_tree mode doesn't need it)
    print("[INFO] Installing Playwright Chromium browser (optional — for screenshot mode) ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
    except subprocess.CalledProcessError:
        print("[WARN] playwright install failed — screenshot mode may not work")

    print("[ OK ] OSWorld dependencies installed")


if __name__ == "__main__":
    main()
