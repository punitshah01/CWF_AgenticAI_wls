#!/usr/bin/env python3
"""
misc/process_emon.py — Post-process raw EMON data with EDP.

Auto-detects the platform, resolves the correct EDP XML path, then invokes
pyedp (preferred) or jruby edp.rb to generate per-socket and per-core CSV views.

Usage:
  python3 misc/process_emon.py --emon-file <path/to/emon.dat>
  python3 misc/process_emon.py --emon-file emon.dat --platform gnr --sockets 2
  python3 misc/process_emon.py --emon-file emon.dat --begin-sample 700 --dirty 400

Output files (same directory as emon-file):
  <name>__mpp_socket_view_summary.csv
  <name>__mpp_core_view_summary.csv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.platform_info import detect_platform
from common.telemetry.emon import EmonCollector


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-process EMON data with EDP")
    parser.add_argument("--emon-file", required=True,
                        help="Path to raw EMON .dat file")
    parser.add_argument("--platform",
                        help="Platform codename (default: auto-detect)")
    parser.add_argument("--sockets", type=int, default=1,
                        help="Number of sockets (default: 1)")
    parser.add_argument("--begin-sample", type=int, default=700,
                        help="First sample to include (default: 700)")
    parser.add_argument("--dirty", type=int, default=400,
                        help="Dirty samples to skip at end (default: 400)")
    parser.add_argument("--views", nargs="+",
                        default=["system-view", "socket-view", "core-view", "uncore-view"],
                        help="EDP views to generate")
    args = parser.parse_args()

    emon_file = Path(args.emon_file)
    if not emon_file.exists():
        print(f"[ERROR] EMON file not found: {emon_file}", file=sys.stderr)
        sys.exit(1)

    platform = args.platform or detect_platform()
    print(f"[process_emon] Platform: {platform}")
    print(f"[process_emon] Sockets : {args.sockets}")
    print(f"[process_emon] File    : {emon_file}")

    collector = EmonCollector()
    ok = collector.process_emon_with_edp(
        emon_file=emon_file,
        platform=platform,
        sockets=args.sockets,
        begin_sample=args.begin_sample,
        dirty_samples=args.dirty,
        views=args.views,
    )

    if not ok:
        print("[ERROR] EDP post-processing failed.", file=sys.stderr)
        sys.exit(1)

    print("[process_emon] Done.")


if __name__ == "__main__":
    main()
