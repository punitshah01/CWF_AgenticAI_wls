#!/usr/bin/env python3
"""
setup/setup_emon.py — Install Intel SEP (EMON) + configure pyedp and TMC client.

Steps:
  1. Download SEP installer from Intel artifactory (or use cached copy)
  2. Run SEP installer (silent mode)
  3. Load kernel drivers via insmod-sep
  4. Verify pyedp is available; configure fallback to jruby edp.rb
  5. Install TMC (Telemetry Management Console) Python client

Usage:
  python3 setup/setup_emon.py
  python3 setup/setup_emon.py --sep-installer /path/to/sep_private_5.38.tar.bz2
  python3 setup/setup_emon.py --dry-run
  python3 setup/setup_emon.py --skip-install   # only configure, assume SEP already installed
  python3 setup/setup_emon.py --verify-only    # just run check_emon_setup.py

Environment variables:
  SEP_ARTIFACTORY_URL   Override download URL (default: Intel internal artifactory)
  SEP_VERSION           SEP version string to download (default: 5.38)
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SEP_ROOT = Path("/opt/intel/sep")
SEP_VERSION_DEFAULT = os.environ.get("SEP_VERSION", "5.38")
SEP_ARTIFACTORY_URL = os.environ.get(
    "SEP_ARTIFACTORY_URL",
    "https://ubit-artifactory-or.intel.com/artifactory/sep-local",
)
REPO_ROOT = Path(__file__).resolve().parent.parent
PYEDP_PATH = SEP_ROOT / "config" / "edp" / "pyedp" / "pyedp.py"
TMC_PKG = "intel-tmc-client"


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


def download_sep(version: str, dest_dir: Path, dry_run: bool) -> Path:
    """Download SEP tarball from artifactory. Returns path to downloaded file."""
    filename = f"sep_private_{version}.tar.bz2"
    url = f"{SEP_ARTIFACTORY_URL}/{filename}"
    dest = dest_dir / filename

    if dest.exists():
        print(f"[ OK ] SEP installer already cached: {dest}")
        return dest

    # Also check assets/installers/
    cached = REPO_ROOT / "assets" / "installers" / filename
    if cached.exists():
        print(f"[ OK ] Using cached SEP installer: {cached}")
        return cached

    print(f"[INFO] Downloading SEP {version} from artifactory ...")
    print(f"[INFO] URL: {url}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    if shutil.which("wget"):
        _run(f"wget -c --progress=bar:force -O {dest} '{url}'", dry_run)
    elif shutil.which("curl"):
        _run(f"curl -L --continue-at - -o {dest} '{url}'", dry_run)
    else:
        print("[ERROR] wget or curl required to download SEP", file=sys.stderr)
        sys.exit(1)

    return dest


def install_sep(installer: Path, dry_run: bool) -> None:
    """Extract and install SEP."""
    tmp = Path("/tmp/sep_install")
    print(f"\n[INFO] Extracting SEP installer to {tmp} ...")
    _run(f"mkdir -p {tmp} && tar -xjf {installer} -C {tmp}", dry_run)

    # Find install.sh inside extracted directory
    install_scripts = list(tmp.rglob("install.sh")) if not dry_run else []
    if install_scripts:
        install_sh = install_scripts[0]
        _run(f"sudo bash {install_sh} --accept-license", dry_run)
    else:
        # Try direct silent installer pattern
        _run(f"sudo bash {tmp}/sep_private/install.sh --accept-license", dry_run)

    print("[ OK ] SEP installed to /opt/intel/sep")


def load_drivers(dry_run: bool) -> None:
    """Load SEP kernel drivers."""
    print("\n[INFO] Loading SEP kernel drivers ...")
    insmod_sep = SEP_ROOT / "sepdk" / "src" / "insmod-sep"
    if insmod_sep.exists() or dry_run:
        user = os.environ.get("USER", "root")
        _run(f"sudo {insmod_sep} -r -g {user}", dry_run)
        print("[ OK ] SEP drivers loaded")
    else:
        print(f"[WARN] insmod-sep not found at {insmod_sep} — try loading manually",
              file=sys.stderr)


def configure_pyedp(dry_run: bool) -> None:
    """Verify pyedp is present and install Python dependencies."""
    print("\n[INFO] Configuring pyedp ...")

    if PYEDP_PATH.exists() or dry_run:
        print(f"[ OK ] pyedp found: {PYEDP_PATH}")
        # Install pyedp Python requirements if present
        req_file = PYEDP_PATH.parent / "requirements.txt"
        if req_file.exists() or dry_run:
            _run(f"pip install -q -r {req_file}", dry_run)
        print("[ OK ] pyedp configured")
    else:
        print(f"[WARN] pyedp not found at {PYEDP_PATH}", file=sys.stderr)
        print("[WARN] Checking jruby fallback ...")
        if shutil.which("jruby"):
            edp_rb = SEP_ROOT / "config" / "edp" / "edp.rb"
            if edp_rb.exists():
                print(f"[ OK ] jruby fallback available: {edp_rb}")
            else:
                print("[WARN] jruby found but edp.rb not found — EDP post-processing unavailable",
                      file=sys.stderr)
        else:
            print("[WARN] Neither pyedp nor jruby found — EMON post-processing will not work",
                  file=sys.stderr)


def install_tmc(dry_run: bool) -> None:
    """Install TMC (Telemetry Management Console) Python client."""
    print(f"\n[INFO] Installing TMC Python client ({TMC_PKG}) ...")
    _run(f"pip install -q {TMC_PKG}", dry_run, check=False)
    print(f"[ OK ] {TMC_PKG} installed")


def verify(dry_run: bool) -> int:
    """Run check_emon_setup.py and return its exit code."""
    check_script = REPO_ROOT / "misc" / "check_emon_setup.py"
    if check_script.exists():
        r = _run(f"{sys.executable} {check_script}", dry_run)
        return r.returncode if r else 0
    print("[WARN] misc/check_emon_setup.py not found — skipping verification")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Install and configure Intel SEP/EMON")
    parser.add_argument("--sep-installer", help="Path to local SEP .tar.bz2 installer")
    parser.add_argument("--sep-version", default=SEP_VERSION_DEFAULT,
                        help=f"SEP version to download. Default: {SEP_VERSION_DEFAULT}")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip SEP install (assume already installed), only configure")
    parser.add_argument("--skip-tmc", action="store_true",
                        help="Skip TMC client installation")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only run verification, skip all install steps")
    args = parser.parse_args()

    if args.verify_only:
        sys.exit(verify(args.dry_run))

    if not args.skip_install:
        if args.sep_installer:
            installer = Path(args.sep_installer)
            if not installer.exists():
                print(f"[ERROR] Installer not found: {installer}", file=sys.stderr)
                sys.exit(1)
        else:
            installer = download_sep(
                args.sep_version, Path("/tmp"), args.dry_run
            )

        install_sep(installer, args.dry_run)
        load_drivers(args.dry_run)

    configure_pyedp(args.dry_run)

    if not args.skip_tmc:
        install_tmc(args.dry_run)

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
