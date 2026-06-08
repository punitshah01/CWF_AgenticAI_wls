#!/usr/bin/env python3
"""
misc/detect_platform.py — Detect CPU platform codename from family/model/stepping.

Usage:
  python3 misc/detect_platform.py            # prints codename to stdout
  python3 misc/detect_platform.py --json     # prints full platform dict as JSON
  python3 misc/detect_platform.py --verbose  # prints family/model/stepping too
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.platform_info import detect_platform, get_platform_info


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect CPU platform codename",
    )
    parser.add_argument("--json", action="store_true",
                        help="Output full platform info as JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show family/model/stepping alongside codename")
    args = parser.parse_args()

    if args.json:
        info = get_platform_info()
        print(json.dumps(info, indent=2))
        return

    codename = detect_platform()

    if args.verbose:
        info = get_platform_info()
        print(f"Codename : {codename}")
        print(f"Family   : {info.get('cpu_family', 'unknown')}")
        print(f"Model    : {info.get('cpu_model', 'unknown')}")
        print(f"Stepping : {info.get('cpu_stepping', 'unknown')}")
    else:
        print(codename)


if __name__ == "__main__":
    main()
