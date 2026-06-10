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

    rc, out, err = _run(f"{emon_bin} --version 2>&1 | head -4")
    combined = (out + " " + err).replace("(", " ").replace(")", " ").replace(",", " ")
    version_str = "unknown"
    version_ok = False

    import re
    # Match patterns like: 5.38  5.58  5_58  "version 5 58"  "K(5.38 release)"
    for pattern in (
        r"(\d+)\.(\d+)",           # canonical:  5.38
        r"(\d+)_(\d+)",            # underscore: 5_58
        r"sep.*?(\d+).*?(\d+)",    # loose:  sep ... 5 ... 58
    ):
        m = re.search(pattern, combined, re.IGNORECASE)
        if m:
            try:
                major, minor = int(m.group(1)), int(m.group(2))
                if 1 <= major <= 20 and 0 <= minor <= 999:   # sanity bounds
                    version_str = f"{major}.{minor}"
                    version_ok = (major, minor) >= MIN_VERSION
                    break
            except (ValueError, IndexError):
                continue

    if version_str == "unknown":
        # Last resort: version is embedded in the installed directory name
        # e.g. sep_private_5_58_beta_linux_...
        m2 = re.search(r"sep[^/]*?(\d+)[._](\d+)",
                       str(list(SEP_ROOT.glob("../*sep*"))[:1]), re.IGNORECASE)
        if m2:
            major, minor = int(m2.group(1)), int(m2.group(2))
            version_str = f"{major}.{minor} (from dir name)"
            version_ok = (major, minor) >= MIN_VERSION

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
    # 1. Search the whole SEP tree for pyedp.py — location varies by SEP release
    pyedp_candidates = list(SEP_ROOT.rglob("pyedp.py"))
    if pyedp_candidates:
        return {"name": "pyedp / edp.rb", "ok": True, "detail": str(pyedp_candidates[0])}

    # 2. Check if pyedp is installed as a Python package (SEP 5.58 beta ships it this way)
    try:
        import importlib.util
        spec = importlib.util.find_spec("pyedp")
        if spec is not None:
            return {"name": "pyedp / edp.rb", "ok": True,
                    "detail": f"pyedp pip package installed ({spec.origin})"}
    except (ModuleNotFoundError, ValueError):
        pass

    # 3. Check if pyedp CLI is on PATH
    pyedp_bin = shutil.which("pyedp")
    if pyedp_bin:
        return {"name": "pyedp / edp.rb", "ok": True,
                "detail": f"pyedp binary found: {pyedp_bin}"}

    # 4. Fallback: jruby edp.rb
    jruby = shutil.which("jruby")
    edp_rb_candidates = list(SEP_ROOT.rglob("edp.rb"))
    if jruby and edp_rb_candidates:
        return {"name": "pyedp (jruby fallback)", "ok": True,
                "detail": f"jruby={jruby}, edp.rb={edp_rb_candidates[0]}"}

    return {"name": "pyedp / edp.rb", "ok": False, "warn_only": True,
            "detail": (
                f"pyedp.py not found under {SEP_ROOT}; "
                "pyedp pip package not installed; "
                f"jruby={jruby}. "
                "EMON collection still works. "
                "For EDP post-processing: locate pyedp in your SEP tarball and run "
                "pip install /path/to/sep/.../pyedp/"
            )}


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
        hard_fail = False
        for c in checks:
            warn_only = c.get("warn_only", False)
            if c["ok"]:
                mark = "[ OK ]"
            elif warn_only:
                mark = "[WARN]"
            else:
                mark = "[FAIL]"
                hard_fail = True
            print(f"  {mark}  {c['name']:<25}  {c['detail']}")
        print()
        if not hard_fail:
            print("  EMON setup: READY  (collection works; see WARN items for optional post-processing)")
        else:
            print("  EMON setup: NOT READY — fix the items marked [FAIL] above")

    hard_fail = any(not c["ok"] and not c.get("warn_only", False) for c in checks)
    sys.exit(0 if not hard_fail else 1)


if __name__ == "__main__":
    main()
