#!/usr/bin/env python3
"""
misc/collect_meminfo.py — Snapshot /proc/meminfo into results/platform/.

Usage:
  python3 misc/collect_meminfo.py [--out-dir results/platform]
  python3 misc/collect_meminfo.py --print   # also print to stdout
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot /proc/meminfo")
    parser.add_argument("--out-dir", default="results/platform",
                        help="Output directory (default: results/platform)")
    parser.add_argument("--print", dest="do_print", action="store_true",
                        help="Also print meminfo to stdout")
    args = parser.parse_args()

    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        print("[ERROR] /proc/meminfo not found — not running on Linux?", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"meminfo_{ts}.txt"

    shutil.copy(meminfo, out_file)
    print(f"[collect_meminfo] Saved to {out_file}")

    if args.do_print:
        print(out_file.read_text())


if __name__ == "__main__":
    main()
