#!/usr/bin/env python3
"""
misc/collect_rapl.py — Snapshot RAPL power from powercap sysfs.

Measures average power over a sampling window by reading energy counters
at start and end, then computing (delta_uJ / duration_s / 1e6) = watts.

Usage:
  python3 misc/collect_rapl.py                  # 10-second sample, CSV to stdout
  python3 misc/collect_rapl.py --duration 30    # 30-second sample
  python3 misc/collect_rapl.py -o out.csv       # save CSV to file
  python3 misc/collect_rapl.py --json           # output as JSON

Output (CSV):
  domain,avg_watts
  package_0,85.23
  dram_0_0,12.44
"""

import argparse
import json
import sys
import time
from pathlib import Path

RAPL_BASE = Path("/sys/class/powercap/intel-rapl")


def discover_domains() -> dict:
    """Discover RAPL energy counter paths. Returns {label: Path}."""
    if not RAPL_BASE.exists():
        return {}
    domains = {}
    for pkg_dir in sorted(RAPL_BASE.glob("intel-rapl:*")):
        energy_file = pkg_dir / "energy_uj"
        if not energy_file.exists():
            continue
        try:
            name = (pkg_dir / "name").read_text().strip()
        except OSError:
            name = "pkg"
        idx = pkg_dir.name.split(":")[-1]
        label = f"{name}_{idx}"
        domains[label] = energy_file
        # Sub-domains (dram, uncore, psys, …)
        for sub_dir in sorted(pkg_dir.glob("intel-rapl:*")):
            sub_energy = sub_dir / "energy_uj"
            if not sub_energy.exists():
                continue
            try:
                sub_name = (sub_dir / "name").read_text().strip()
            except OSError:
                sub_name = "sub"
            sub_label = f"{sub_name}_{sub_dir.name.replace(':', '_')}"
            domains[sub_label] = sub_energy
    return domains


def read_energy(domains: dict) -> dict:
    """Read current energy_uj for each domain."""
    snapshot = {}
    for label, path in domains.items():
        try:
            snapshot[label] = int(path.read_text().strip())
        except OSError:
            snapshot[label] = 0
    return snapshot


def max_energy_range(energy_path: Path) -> int:
    """Read max_energy_range_uj for wrap-around correction."""
    try:
        return int((energy_path.parent / "max_energy_range_uj").read_text().strip())
    except OSError:
        return 2 ** 32


def main() -> None:
    parser = argparse.ArgumentParser(description="RAPL power snapshot")
    parser.add_argument("--duration", "-d", type=float, default=10.0,
                        help="Sampling duration in seconds (default: 10)")
    parser.add_argument("-o", "--out", help="Save CSV output to this file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    domains = discover_domains()
    if not domains:
        print("[ERROR] RAPL sysfs not found at "
              f"{RAPL_BASE} — check kernel config or run as root", file=sys.stderr)
        sys.exit(1)

    e0 = read_energy(domains)
    time.sleep(args.duration)
    e1 = read_energy(domains)

    results = []
    for label in sorted(domains):
        energy_path = domains[label]
        delta = e1[label] - e0[label]
        if delta < 0:
            delta += max_energy_range(energy_path)
        avg_watts = delta / args.duration / 1_000_000
        results.append({"domain": label, "avg_watts": round(avg_watts, 2)})

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        lines = ["domain,avg_watts"] + [f"{r['domain']},{r['avg_watts']}" for r in results]
        output = "\n".join(lines)
        print(output)
        if args.out:
            Path(args.out).write_text(output + "\n")
            print(f"[collect_rapl] Saved to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
