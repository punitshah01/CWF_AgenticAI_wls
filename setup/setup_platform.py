#!/usr/bin/env python3
"""
setup/setup_platform.py — Apply system tuning for consistent benchmark results on CWF.

Run as root (or with sudo) before any benchmark run.
Restores are NOT automatic — reboot to reset, or manually revert.

Usage:
  python3 setup/setup_platform.py
  python3 setup/setup_platform.py --no-turbo   # also disable Intel turbo boost
"""

import argparse
import sys
from pathlib import Path


def _write_sysfs(path: str, value: str) -> bool:
    """Write value to a sysfs/procfs path. Returns True on success."""
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except PermissionError:
        print(f"[WARN] Permission denied writing {path} — run as root", file=sys.stderr)
        return False
    except OSError as e:
        print(f"[WARN] Could not write {path}: {e}", file=sys.stderr)
        return False


def _read_sysfs(path: str) -> str:
    """Read value from a sysfs/procfs path. Returns 'n/a' on failure."""
    try:
        return Path(path).read_text().strip()
    except OSError:
        return "n/a"


def main() -> None:
    if sys.platform != "linux":
        print("[ERROR] setup_platform.py is Linux-only.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Apply platform tuning for CWF benchmark reproducibility.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--no-turbo",
        action="store_true",
        help="Disable Intel turbo boost (default: leave unchanged)",
    )
    args = parser.parse_args()

    print("=== CWF Platform Tuning ===")

    # 1. CPU governor → performance
    print("[1/4] Setting CPU governor to 'performance' ...")
    gov_paths = sorted(Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor"))
    if not gov_paths:
        print("      WARNING: No cpufreq governor paths found — is the kernel driver loaded?")
    for gov_path in gov_paths:
        _write_sysfs(str(gov_path), "performance")
    sample = _read_sysfs("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    print(f"      Governor cpu0: {sample}")

    # 2. Disable turbo boost (optional)
    turbo_path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    if args.no_turbo:
        print("[2/4] Disabling Intel turbo boost ...")
        if Path(turbo_path).exists():
            _write_sysfs(turbo_path, "1")
            print(f"      no_turbo: {_read_sysfs(turbo_path)}")
        else:
            print(f"      WARNING: {turbo_path} not found — turbo state unchanged")
    else:
        print("[2/4] Turbo boost: unchanged (pass --no-turbo to disable)")

    # 3. Disable ASLR
    print("[3/4] Disabling ASLR (randomize_va_space → 0) ...")
    _write_sysfs("/proc/sys/kernel/randomize_va_space", "0")
    print(f"      randomize_va_space: {_read_sysfs('/proc/sys/kernel/randomize_va_space')}")

    # 4. Transparent Huge Pages → madvise
    print("[4/4] Setting THP to madvise ...")
    thp_base = Path("/sys/kernel/mm/transparent_hugepage")
    if thp_base.is_dir():
        _write_sysfs(str(thp_base / "enabled"), "madvise")
        _write_sysfs(str(thp_base / "defrag"), "defer+madvise")
        print(f"      THP enabled: {_read_sysfs(str(thp_base / 'enabled'))}")
    else:
        print("      WARNING: THP sysfs not found — skipping")

    print()
    print("[OK] Platform tuning complete. Reboot to restore defaults.")


if __name__ == "__main__":
    main()
