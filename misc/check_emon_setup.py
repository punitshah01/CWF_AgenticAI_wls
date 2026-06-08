#!/usr/bin/env python3
"""
misc/check_emon_setup.py — Verify Intel SEP/EMON installation and driver state.

Checks:
  1. SEP installed at /opt/intel/sep
  2. Minimum version >= 5.32
  3. sep and pax kernel drivers loaded
  4. pyedp available (preferred) or jruby edp.rb (fallback)

Exit codes:
  0 — all checks passed
  1 — one or more checks failed

Usage:
  python3 misc/check_emon_setup.py
  python3 misc/check_emon_setup.py --load-drivers  # attempt to load drivers if not loaded
  python3 misc/check_emon_setup.py --json           # machine-readable output
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SEP_ROOT = Path("/opt/intel/sep")
MIN_VERSION = (5, 32)


def _run(cmd: str) -> tuple:
    """Run a shell command. Returns (returncode, stdout, stderr)."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def check_sep_installed() -> dict:
    emon_bin = SEP_ROOT / "bin64" / "emon"
    present = emon_bin.exists()
    return {
        "name": "SEP installed",
        "ok": present,
        "detail": str(emon_bin) if present else f"Not found at {SEP_ROOT}",
    }


def check_sep_version() -> dict:
    emon_bin = SEP_ROOT / "bin64" / "emon"
    if not emon_bin.exists():
        return {"name": "SEP version", "ok": False, "detail": "emon binary not found"}

    rc, out, _ = _run(f"{emon_bin} --version 2>&1 | head -2")
    # Example: "EMON version K (5.38 release) ..."
    version_str = "unknown"
    version_ok = False
    for token in out.split():
        if "." in token:
            try:
                parts = token.split(".")
                major, minor = int(parts[0]), int(parts[1].split(")")[0].split(" ")[0])
                version_str = f"{major}.{minor}"
                version_ok = (major, minor) >= MIN_VERSION
                break
            except ValueError:
                continue

    return {
        "name": "SEP version",
        "ok": version_ok,
        "detail": f"{version_str} (need >= {MIN_VERSION[0]}.{MIN_VERSION[1]})",
    }


def check_drivers_loaded() -> dict:
    rc_sep, _, _ = _run("lsmod 2>/dev/null | grep -q '^sep'")
    rc_pax, _, _ = _run("lsmod 2>/dev/null | grep -q '^pax'")
    ok = (rc_sep == 0) and (rc_pax == 0)
    detail_parts = []
    if rc_sep != 0:
        detail_parts.append("sep driver NOT loaded")
    if rc_pax != 0:
        detail_parts.append("pax driver NOT loaded")
    if ok:
        detail_parts.append("sep + pax drivers loaded")
    return {"name": "SEP drivers", "ok": ok, "detail": "; ".join(detail_parts)}


def load_drivers() -> bool:
    """Attempt to load SEP drivers. Returns True on success."""
    driver_script = SEP_ROOT / "sepdk" / "src" / "insmod-sep"
    if driver_script.exists():
        rc, _, err = _run(f"sudo {driver_script} -r -g $(whoami)")
        return rc == 0
    # Fallback: try emon -i
    rc, _, _ = _run(f"sudo {SEP_ROOT / 'bin64' / 'emon'} -i")
    return rc == 0


def check_pyedp() -> dict:
    pyedp = SEP_ROOT / "config" / "edp" / "pyedp" / "pyedp.py"
    if pyedp.exists():
        return {"name": "pyedp", "ok": True, "detail": str(pyedp)}

    # Fallback: jruby edp.rb
    jruby = shutil.which("jruby")
    edp_rb = SEP_ROOT / "config" / "edp" / "edp.rb"
    if jruby and edp_rb.exists():
        return {"name": "pyedp (jruby fallback)", "ok": True,
                "detail": f"jruby={jruby}, edp.rb={edp_rb}"}

    return {"name": "pyedp / edp.rb", "ok": False,
            "detail": f"Neither found (pyedp at {pyedp}, jruby={jruby})"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify EMON/SEP setup")
    parser.add_argument("--load-drivers", action="store_true",
                        help="Attempt to load SEP drivers if not loaded")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    checks = [
        check_sep_installed(),
        check_sep_version(),
        check_drivers_loaded(),
        check_pyedp(),
    ]

    # Optionally try to load drivers if the check failed
    if args.load_drivers:
        driver_check = next((c for c in checks if c["name"] == "SEP drivers"), None)
        if driver_check and not driver_check["ok"]:
            print("[INFO] Attempting to load SEP drivers...", flush=True)
            if load_drivers():
                checks = [c if c["name"] != "SEP drivers" else check_drivers_loaded()
                          for c in checks]
            else:
                print("[WARN] Failed to load drivers — run with sudo or check insmod-sep",
                      flush=True)

    if args.json:
        print(json.dumps(checks, indent=2))
    else:
        print()
        all_ok = True
        for c in checks:
            mark = "[ OK ]" if c["ok"] else "[FAIL]"
            print(f"  {mark}  {c['name']:<25}  {c['detail']}")
            if not c["ok"]:
                all_ok = False
        print()
        if all_ok:
            print("  EMON setup: READY")
        else:
            print("  EMON setup: NOT READY — fix the items marked [FAIL] above")

    all_ok = all(c["ok"] for c in checks)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
