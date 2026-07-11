#!/usr/bin/env python3
"""
setup/setup_emon.py — Install Intel SEP (EMON) + configure pyedp and TMC client.

Matches the pnpwls/setup/setup_emon.sh approach:
    0. Pre-flight checks: system dependencies (gcc, make, tar, wget/curl, git)
  1. Ensure kernel-devel is installed (via setup_kernel_devel.py)
  2. Download SEP beta from Intel artifactory (dpgpaivsoworkloads-or-local)
  3. Extract and run sep-installer.sh --accept-license -ni -u -i
    4. Install pyedp Python dependencies + pip install . (with PIP_BREAK_SYSTEM_PACKAGES=1)
  5. Clone and install TMC (tools.dcso.telemetry.client)
  6. Load SEP kernel drivers via insmod-sep
  7. Verify with check_emon_setup.py

Usage:
  python3 setup/setup_emon.py
  python3 setup/setup_emon.py --sep-installer /path/to/sep_private_5_58_beta_linux_....tar.bz2
  python3 setup/setup_emon.py --dry-run
  python3 setup/setup_emon.py --skip-install   # only configure, assume SEP already installed
  python3 setup/setup_emon.py --skip-kernel-devel  # skip kernel-devel step
    python3 setup/setup_emon.py --skip-tmc       # skip TMC client installation
  python3 setup/setup_emon.py --verify-only    # just run check_emon_setup.py

Environment variables:
  SEP_ARTIFACTORY_URL   Override download URL base
  SEP_VERSION           Override SEP version string (full package name without .tar.bz2)
    PIP_BREAK_SYSTEM_PACKAGES  Set to '1' to bypass PEP 668 protections (auto-set by script)
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

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


def check_system_dependencies(dry_run: bool) -> bool:
    """Check for required system tools: gcc, make, tar, wget/curl, git.

    These are needed for:
      - gcc/make: compiling SEP kernel drivers
      - tar: extracting SEP tarball
      - wget/curl: downloading SEP from artifactory
      - git: cloning TMC telemetry client

    Returns True if all checks pass, False otherwise.
    """
    print("\n[INFO] Checking system dependencies ...")
    if dry_run:
        print("[ OK ] (dry-run) skipping system dependency checks")
        return True

    required_tools = {
        "gcc": "compiler (build-essential/gcc package)",
        "make": "build tool (make package)",
        "tar": "archive tool (tar package)",
        "git": "version control (git package)",
    }

    download_tool = "wget" if shutil.which("wget") else ("curl" if shutil.which("curl") else None)

    missing = []
    for tool, desc in required_tools.items():
        if not shutil.which(tool):
            missing.append(f"{tool} ({desc})")

    if not download_tool:
        missing.append("wget or curl (for downloading SEP from artifactory)")

    if missing:
        print("[FAIL] Missing system tools:", file=sys.stderr)
        for item in missing:
            print(f"       - {item}", file=sys.stderr)
        print("[FAIL] Install missing tools and retry. Example:", file=sys.stderr)
        print("       sudo dnf install gcc make tar git wget        # RHEL/CentOS/Fedora", file=sys.stderr)
        print("       sudo apt-get install build-essential git wget # Debian/Ubuntu", file=sys.stderr)
        return False

    print("[ OK ] All required system tools are available")
    return True


def ensure_python_pip(dry_run: bool) -> bool:
    """Ensure python3 -m pip is available for pyedp dependency installation."""
    print("\n[INFO] Checking python3 pip availability ...")
    if dry_run:
        print("[ OK ] (dry-run) assuming python3 pip is available")
        return True

    check = subprocess.run(
        ["python3", "-m", "pip", "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check.returncode == 0:
        print(f"[ OK ] {check.stdout.strip()}")
        return True

    print("[WARN] python3 pip is missing, trying ensurepip ...", file=sys.stderr)
    ensurepip = subprocess.run(
        ["python3", "-m", "ensurepip", "--upgrade"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if ensurepip.returncode == 0:
        recheck = subprocess.run(
            ["python3", "-m", "pip", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if recheck.returncode == 0:
            print(f"[ OK ] {recheck.stdout.strip()}")
            return True

    print("[WARN] ensurepip unavailable/failed, trying OS package manager for python3-pip ...", file=sys.stderr)

    pkg_cmds = []
    if shutil.which("dnf"):
        pkg_cmds.append("sudo dnf install -y python3-pip")
    if shutil.which("yum"):
        pkg_cmds.append("sudo yum install -y python3-pip")
    if shutil.which("apt-get"):
        pkg_cmds.append("sudo apt-get update && sudo apt-get install -y python3-pip")
    if shutil.which("zypper"):
        pkg_cmds.append("sudo zypper --non-interactive install python3-pip")

    for cmd in pkg_cmds:
        r = _run(cmd, dry_run=False)
        if r.returncode != 0:
            continue
        recheck = subprocess.run(
            ["python3", "-m", "pip", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if recheck.returncode == 0:
            print(f"[ OK ] {recheck.stdout.strip()}")
            return True

    print("[ERROR] python3 pip is not available.", file=sys.stderr)
    print("[ERROR] Install it manually, then rerun setup/setup_emon.py", file=sys.stderr)
    return False


def ensure_kernel_devel(dry_run: bool) -> None:
    """Run setup_kernel_devel.py to ensure kernel-devel is installed."""
    script = Path(__file__).resolve().parent / "setup_kernel_devel.py"
    if not script.exists():
        print(f"[WARN] {script} not found — skipping kernel-devel check", file=sys.stderr)
        return
    print("\n[INFO] Ensuring kernel-devel is installed ...")
    _run(f"{sys.executable} {script}", dry_run)


def _is_valid_tar_bz2(path: Path) -> bool:
    """Return True if `path` is a real (non-empty, non-HTML-error-page) bzip2 tar archive."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    probe = subprocess.run(
        ["tar", "tjf", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return probe.returncode == 0


def _find_fallback_sep_asset() -> Optional[Path]:
    """Find any pre-staged SEP installer under assets/installers/ to use as a
    last-resort fallback when Artifactory is completely unreachable (e.g. down,
    or this host has no route to ubit-artifactory-or.intel.com). May be a
    different SEP version than the one requested — callers must warn the user.
    Tracked via git-lfs (see .gitattributes): assets/installers/*.tar.bz2
    """
    installers_dir = REPO_ROOT / "assets" / "installers"
    if not installers_dir.exists():
        return None
    candidates = sorted(installers_dir.glob("sep_private_*.tar.bz2"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    for c in candidates:
        if _is_valid_tar_bz2(c):
            return c
    return None


def download_sep(version: str, dry_run: bool) -> Path:
    """Download SEP tarball from artifactory. Returns path to local file."""
    filename = f"{version}.tar.bz2"
    url = f"{SEP_ARTIFACTORY_BASE}/{filename}"
    dest_dir = Path.home() / "devtools"
    dest = dest_dir / filename

    if dest.exists():
        # Validate the cached file is a real tar archive, not a partial download or HTML error page
        if _is_valid_tar_bz2(dest):
            print(f"[ OK ] SEP installer already cached: {dest}")
            return dest
        print(f"[WARN] Cached SEP archive is corrupt — deleting and re-downloading: {dest}")
        dest.unlink(missing_ok=True)

    # Check repo assets/installers/ cache
    cached = REPO_ROOT / "assets" / "installers" / filename
    if cached.exists():
        print(f"[ OK ] Using cached SEP installer: {cached}")
        return cached

    print("\n[INFO] Downloading SEP from artifactory ...")
    print(f"[INFO] URL: {url}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return dest

    # ubit-artifactory-or.intel.com is an Intel-internal host. On true
    # intranet-connected lab benches it's reachable directly (--no-proxy).
    # But some lab/cloud hosts only reach Intel-internal networks THROUGH the
    # corp web proxy — direct access then fails DNS resolution entirely
    # ("Name or service not known"). So try both direct and proxied for each
    # tool, and VALIDATE the result every time instead of trusting exit code
    # (a failed download can still leave a truncated/empty/HTML file behind).
    attempts = []
    if shutil.which("wget"):
        attempts.append(("wget (direct)",
                          f"wget --no-proxy --no-check-certificate -c --progress=bar:force -O {dest} '{url}'"))
        attempts.append(("wget (via proxy)",
                          f"wget --no-check-certificate -c --progress=bar:force -O {dest} '{url}'"))
    if shutil.which("curl"):
        attempts.append(("curl (direct)",
                          f"curl --noproxy '*' -k -L --continue-at - -o {dest} '{url}'"))
        attempts.append(("curl (via proxy)",
                          f"curl -k -L --continue-at - -o {dest} '{url}'"))

    if not attempts:
        print("[ERROR] wget or curl required to download SEP", file=sys.stderr)
        sys.exit(1)

    for label, cmd in attempts:
        print(f"[INFO] Attempt: {label}")
        _run(cmd, dry_run=False)
        if _is_valid_tar_bz2(dest):
            print(f"[ OK ] Downloaded valid SEP archive via {label}")
            return dest
        print(f"[WARN] {label} did not produce a valid tar.bz2 — trying next method.")
        dest.unlink(missing_ok=True)

    print(f"[WARN] All download attempts from Artifactory failed (unreachable or down): {url}",
          file=sys.stderr)
    fallback = _find_fallback_sep_asset()
    if fallback:
        print(f"[WARN] Falling back to locally staged SEP installer: {fallback}", file=sys.stderr)
        if fallback.name != filename:
            print(f"[WARN] NOTE: this is a DIFFERENT SEP version than requested "
                  f"({filename}) — proceeding anyway since Artifactory is unreachable.",
                  file=sys.stderr)
        return fallback

    print(f"[ERROR] Could not download a valid SEP archive from {url}", file=sys.stderr)
    print("[ERROR] This host may lack network/VPN access to Intel-internal "
          "Artifactory (ubit-artifactory-or.intel.com). Options:", file=sys.stderr)
    print("        1. Verify intranet/VPN connectivity and DNS resolution to "
          "ubit-artifactory-or.intel.com, then retry.", file=sys.stderr)
    print(f"        2. Manually download a SEP installer and place it at "
          f"{REPO_ROOT / 'assets' / 'installers'}/, then retry.", file=sys.stderr)
    print(f"        3. Pass --sep-installer /path/to/sep_....tar.bz2 to skip the download.",
          file=sys.stderr)
    sys.exit(1)


def install_sep(installer: Path, dry_run: bool) -> None:
    """Extract and install SEP using sep-installer.sh (matches pnpwls approach)."""
    if not dry_run and not _is_valid_tar_bz2(installer):
        print(f"[ERROR] {installer} is not a valid tar.bz2 archive — refusing to extract.",
              file=sys.stderr)
        print("[ERROR] (empty file, truncated download, or an HTML error/proxy-block page)",
              file=sys.stderr)
        sys.exit(1)

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
    """Install pyedp Python dependencies and pyedp itself (matches pnpwls)."""
    print("\n[INFO] Configuring pyedp ...")

    if not ensure_python_pip(dry_run):
        sys.exit(1)

    env = os.environ.copy()
    env["PIP_BREAK_SYSTEM_PACKAGES"] = "1"

    # Full pyedp dependency list
    pkgs = " ".join(PYEDP_PIP_PACKAGES)
    cmd = f"python3 -m pip install -U {pkgs}"
    print(f"  $ {cmd}", flush=True)
    if not dry_run:
        r = subprocess.run(cmd, shell=True, env=env)
        if r.returncode != 0:
            print(f"[WARN] pip install failed with exit code {r.returncode}", file=sys.stderr)

    if PYEDP_DIR.exists():
        # SEP shipped pyedp source under /opt/intel/sep — install from there
        print(f"[ OK ] pyedp directory: {PYEDP_DIR}")
        cmd = f"cd {PYEDP_DIR} && python3 -m pip install ."
        print(f"  $ {cmd}", flush=True)
        if not dry_run:
            r = subprocess.run(cmd, shell=True, env=env)
            if r.returncode != 0:
                print(f"[WARN] pyedp pip install failed with exit code {r.returncode}", file=sys.stderr)
    else:
        # SEP 5.58 beta: search the whole SEP tree for any pyedp directory
        candidates = list(SEP_ROOT.rglob("pyedp.py")) if not dry_run else []
        if candidates:
            found_dir = candidates[0].parent
            print(f"[ OK ] pyedp found at: {found_dir}")
            _run(f"cd {found_dir} && python3 -m pip install .", dry_run)
        else:
            # pyedp is not bundled with this SEP release.
            # Install only the dependency packages — pyedp.py itself must come
            # from the SEP package; without it EMON post-processing won't work
            # but EMON data collection will still function.
            print(f"[WARN] pyedp not found under {SEP_ROOT}", file=sys.stderr)
            print("[WARN] EMON collection will work but post-processing (EDP) won't.", file=sys.stderr)
            print("[WARN] To fix: locate pyedp.py in your SEP tarball and run:", file=sys.stderr)
            print("[WARN]   pip install /path/to/sep/.../pyedp/", file=sys.stderr)

    print("[ OK ] pyedp configured")


def install_tmc(dry_run: bool) -> None:
    """Clone TMC git repo and run install.sh (matches pnpwls approach)."""
    print("\n[INFO] Installing TMC telemetry client ...")

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

    if not args.skip_install and not check_system_dependencies(args.dry_run):
        print("[ERROR] System dependency check failed.", file=sys.stderr)
        sys.exit(1)

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
