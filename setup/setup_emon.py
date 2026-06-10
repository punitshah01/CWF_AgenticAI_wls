#!/usr/bin/env python3
"""
setup/setup_emon.py — Install Intel SEP (EMON) + configure pyedp and TMC client.

Matches the pnpwls/setup/setup_emon.sh approach:
  1. Ensure kernel-devel is installed (via setup_kernel_devel.py)
  2. Download SEP beta from Intel artifactory (dpgpaivsoworkloads-or-local)
  3. Extract and run sep-installer.sh --accept-license -ni -u -i
  4. Install pyedp Python dependencies + pip install .
  5. Clone and install TMC (tools.dcso.telemetry.client)
  6. Load SEP kernel drivers via insmod-sep
  7. Verify with check_emon_setup.py

Usage:
  python3 setup/setup_emon.py
  python3 setup/setup_emon.py --sep-installer /path/to/sep_private_5_58_beta_linux_....tar.bz2
  python3 setup/setup_emon.py --dry-run
  python3 setup/setup_emon.py --skip-install   # only configure, assume SEP already installed
  python3 setup/setup_emon.py --skip-kernel-devel  # skip kernel-devel step
  python3 setup/setup_emon.py --verify-only    # just run check_emon_setup.py

Environment variables:
  SEP_ARTIFACTORY_URL   Override download URL base
  SEP_VERSION           Override SEP version string (full package name without .tar.bz2)
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SEP_ROOT = Path("/opt/intel/sep")

# SEP beta version — matches pnpwls/setup/setup_emon.sh
SEP_VERSION_DEFAULT = os.environ.get(
    "SEP_VERSION",
    "sep_private_5_58_beta_linux_020402465cf386d3e",
)

# Artifactory URL — matches pnpwls (dpgpaivsoworkloads-or-local)
SEP_ARTIFACTORY_BASE = os.environ.get(
    "SEP_ARTIFACTORY_URL",
    "https://ubit-artifactory-or.intel.com/artifactory/dpgpaivsoworkloads-or-local/utils/emon",
)

# TMC client git repo — matches pnpwls
TMC_GIT_URL = "https://github.com/intel-sandbox/tools.dcso.telemetry.client.git"
TMC_CLONE_DIR = Path.home() / "tmc"

REPO_ROOT = Path(__file__).resolve().parent.parent
PYEDP_DIR = SEP_ROOT / "config" / "edp" / "pyedp"
PYEDP_PATH = PYEDP_DIR / "pyedp.py"

# Full pyedp Python dependency list — matches pnpwls/setup/setup_emon.sh
PYEDP_PIP_PACKAGES = [
    "numpy", "pandas", "defusedxml", "pytz", "xlsxwriter",
    "multiprocess", "tables", "natsort", "tqdm", "dataclasses",
    "polars", "openpyxl", "pyarrow", "jsonschema",
]


def _run(cmd: str, dry_run: bool = False, check: bool = False,
         capture: bool = False) -> subprocess.CompletedProcess:
    print(f"  $ {cmd}", flush=True)
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0)
    return subprocess.run(
        cmd, shell=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )


def ensure_kernel_devel(dry_run: bool) -> None:
    """Run setup_kernel_devel.py to ensure kernel-devel is installed."""
    script = Path(__file__).resolve().parent / "setup_kernel_devel.py"
    if not script.exists():
        print(f"[WARN] {script} not found — skipping kernel-devel check", file=sys.stderr)
        return
    print("\n[INFO] Ensuring kernel-devel is installed ...")
    _run(f"{sys.executable} {script}", dry_run)


def download_sep(version: str, dry_run: bool) -> Path:
    """Download SEP tarball from artifactory. Returns path to local file."""
    filename = f"{version}.tar.bz2"
    url = f"{SEP_ARTIFACTORY_BASE}/{filename}"
    dest_dir = Path.home() / "devtools"
    dest = dest_dir / filename

    if dest.exists():
        print(f"[ OK ] SEP installer already cached: {dest}")
        return dest

    # Check repo assets/installers/ cache
    cached = REPO_ROOT / "assets" / "installers" / filename
    if cached.exists():
        print(f"[ OK ] Using cached SEP installer: {cached}")
        return cached

    print(f"\n[INFO] Downloading SEP from artifactory ...")
    print(f"[INFO] URL: {url}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    if shutil.which("wget"):
        _run(f"wget --no-proxy -c --progress=bar:force -O {dest} '{url}'", dry_run)
    elif shutil.which("curl"):
        _run(f"curl --noproxy '*' -L --continue-at - -o {dest} '{url}'", dry_run)
    else:
        print("[ERROR] wget or curl required to download SEP", file=sys.stderr)
        sys.exit(1)

    return dest


def install_sep(installer: Path, dry_run: bool) -> None:
    """Extract and install SEP using sep-installer.sh (matches pnpwls approach)."""
    version_dir = installer.stem.replace(".tar", "")   # strip .tar.bz2
    extract_dir = Path.home() / "devtools" / version_dir

    print(f"\n[INFO] Extracting SEP to {extract_dir} ...")
    _run(f"mkdir -p {extract_dir.parent} && "
         f"tar xvf {installer} -C {extract_dir.parent}", dry_run)

    # sep-installer.sh is the correct script name for SEP 5.x beta packages
    installer_sh = extract_dir / "sep-installer.sh"

    if not dry_run and not installer_sh.exists():
        # Fallback: find any *installer*.sh in extracted tree
        candidates = list(extract_dir.rglob("*installer*.sh"))
        if candidates:
            installer_sh = candidates[0]
        else:
            print(f"[ERROR] sep-installer.sh not found under {extract_dir}", file=sys.stderr)
            sys.exit(1)

    # Exact flags from pnpwls/setup/setup_emon.sh
    _run(f"cd {extract_dir} && ./sep-installer.sh --accept-license -ni -u -i", dry_run)
    print("[ OK ] SEP installed to /opt/intel/sep")


def load_drivers(dry_run: bool) -> None:
    """Load SEP kernel drivers via insmod-sep."""
    print("\n[INFO] Loading SEP kernel drivers ...")
    insmod_sep = SEP_ROOT / "sepdk" / "src" / "insmod-sep"
    if insmod_sep.exists() or dry_run:
        user = os.environ.get("USER", "root")
        _run(f"sudo {insmod_sep} -r -g {user}", dry_run)
        print("[ OK ] SEP drivers loaded")
    else:
        print(f"[WARN] insmod-sep not found at {insmod_sep} — try: sudo emon -i",
              file=sys.stderr)
        _run(f"sudo {SEP_ROOT}/bin64/emon -i", dry_run)


def configure_pyedp(dry_run: bool) -> None:
    """Install pyedp Python dependencies and run pip install . (matches pnpwls)."""
    print("\n[INFO] Configuring pyedp ...")

    if not PYEDP_DIR.exists() and not dry_run:
        print(f"[WARN] pyedp directory not found: {PYEDP_DIR}", file=sys.stderr)
        print("[WARN] SEP may not be installed yet — skipping pyedp setup", file=sys.stderr)
        return

    print(f"[ OK ] pyedp directory: {PYEDP_DIR}")

    # Step 1: install all required packages (matches pnpwls package list exactly)
    pkgs = " ".join(PYEDP_PIP_PACKAGES)
    _run(f"python3 -m pip install -U {pkgs}", dry_run)

    # Also install jsonschema if missing (pnpwls conditional install)
    _run("python3 -m pip install -U jsonschema", dry_run)

    # Step 2: install pyedp itself (pip install .)
    _run(f"cd {PYEDP_DIR} && python3 -m pip install .", dry_run)

    print("[ OK ] pyedp configured")


def install_tmc(dry_run: bool) -> None:
    """Clone TMC git repo and run install.sh (matches pnpwls approach)."""
    print(f"\n[INFO] Installing TMC telemetry client ...")

    if TMC_CLONE_DIR.exists() and not dry_run:
        print(f"[ OK ] TMC already cloned at {TMC_CLONE_DIR} — pulling latest ...")
        _run(f"cd {TMC_CLONE_DIR} && git pull", dry_run)
    else:
        print(f"[INFO] Cloning TMC from {TMC_GIT_URL} ...")
        _run(f"git clone {TMC_GIT_URL} {TMC_CLONE_DIR}", dry_run)

    _run(f"cd {TMC_CLONE_DIR} && bash install.sh", dry_run)
    print("[ OK ] TMC installed")


def verify(dry_run: bool) -> int:
    """Run check_emon_setup.py and return its exit code."""
    check_script = REPO_ROOT / "misc" / "check_emon_setup.py"
    if check_script.exists():
        r = _run(f"{sys.executable} {check_script}", dry_run)
        return r.returncode if r else 0
    print("[WARN] misc/check_emon_setup.py not found — skipping verification")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install and configure Intel SEP/EMON (matches pnpwls setup_emon.sh)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--sep-installer",
                        help="Path to local SEP .tar.bz2 (skips download)")
    parser.add_argument("--sep-version", default=SEP_VERSION_DEFAULT,
                        help="Full SEP version string (package name without .tar.bz2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip SEP download+install (assume already installed)")
    parser.add_argument("--skip-kernel-devel", action="store_true",
                        help="Skip kernel-devel check/install step")
    parser.add_argument("--skip-tmc", action="store_true",
                        help="Skip TMC client installation")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only run verification, skip all install steps")
    args = parser.parse_args()

    if args.verify_only:
        sys.exit(verify(args.dry_run))

    # Step 1: kernel-devel (required to build SEP drivers)
    if not args.skip_kernel_devel and not args.skip_install:
        ensure_kernel_devel(args.dry_run)

    # Step 2: Download + install SEP
    if not args.skip_install:
        if args.sep_installer:
            installer = Path(args.sep_installer)
            if not installer.exists() and not args.dry_run:
                print(f"[ERROR] Installer not found: {installer}", file=sys.stderr)
                sys.exit(1)
        else:
            installer = download_sep(args.sep_version, args.dry_run)

        install_sep(installer, args.dry_run)

    # Step 3: pyedp Python setup
    configure_pyedp(args.dry_run)

    # Step 4: TMC telemetry client
    if not args.skip_tmc:
        install_tmc(args.dry_run)

    # Step 5: Load kernel drivers
    if not args.skip_install:
        load_drivers(args.dry_run)

    # Step 6: Verify
    print("\n[INFO] Verifying SEP setup ...")
    rc = verify(args.dry_run)

    if rc == 0:
        print("\n[ OK ] EMON/SEP setup complete.")
        print(f"[ OK ] SEP root : {SEP_ROOT}")
        print(f"[ OK ] pyedp    : {PYEDP_PATH}")
    else:
        print("\n[WARN] Some checks failed — see output above.", file=sys.stderr)
        sys.exit(rc)


if __name__ == "__main__":
    main()
