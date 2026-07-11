#!/usr/bin/env python3
"""
scripts/setup.py — CWF Agentic AI: Common Infrastructure Setup
===============================================================
Installs ONLY the shared platform dependencies needed by all benchmarks:
  - Base system packages (numactl, hwloc, msr-tools, git, curl, ...)
  - Docker CE
  - Conda base environment (Python 3.11)
  - git-lfs
  - Common Python packages (pyyaml, psutil, requests, tqdm, huggingface_hub)
  - Intel SEP/EMON telemetry stack (via setup/setup_emon.py)

Benchmark-specific deps are handled by each benchmark's own setup.py:
  benchmarks/webarena/setup.py
  benchmarks/swe-bench/setup.py
  benchmarks/osworld/setup.py
  benchmarks/appworld/setup.py
  benchmarks/t-bench/setup.py

Supports: CentOS/RHEL 8/9 (dnf) and Ubuntu 20.04/22.04/24.04 (apt).

Usage:
  python3 scripts/setup.py                     # common infra only
  python3 scripts/setup.py --install-emon      # common infra + EMON/SEP
  python3 scripts/setup.py --dry-run           # preview commands
  python3 scripts/setup.py --skip-docker       # if Docker already installed
  python3 scripts/setup.py --skip-conda        # if conda env already exists
  python3 scripts/setup.py --conda-env myenv   # custom conda env name

Platform: Clearwater Forest (CWF) | E-core Darkmont | No SMT
POC: Amruta Misra | DPG PAIV SO
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

if sys.version_info < (3, 6):
    sys.exit(
        f"[ERROR] Python 3.6+ required to run setup.py. Current: {sys.version.split()[0]}"
    )
# Note: the conda env created will use Python 3.11. The system Python running
# this script only needs to be 3.6+ since no 3.10+ syntax is used here.

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONDA_ENV_DEFAULT      = "agentic"
PYTHON_VERSION_DEFAULT = "3.11"

MINICONDA_LOCAL = os.environ.get(
    "MINICONDA_LOCAL",
    "assets/installers/Miniconda3-latest-Linux-x86_64.sh",
)

# Base system packages — same on every CWF node regardless of benchmark
# Format: {ubuntu_pkg: centos_pkg}  (None = same name on both distros)
# NOTE: 'perf' is intentionally NOT here — there is no 'perf' apt package on
# Ubuntu (it ships as linux-tools-<kernel>); it is installed separately by
# install_perf_tools() so a missing/unmatched kernel-tools package can never
# block the rest of this list (apt-get install fails atomically on any
# unlocatable package name).
BASE_SYSTEM_PKGS: Dict[str, Optional[str]] = {
    "git":             None,
    "git-lfs":         None,
    "curl":            None,
    "wget":            None,
    "build-essential": "gcc gcc-c++ make",
    "cmake":           None,
    "pkg-config":      "pkgconfig",
    "python3-pip":     "python3-pip",
    "python3-dev":     "python3-devel",
    "htop":            None,
    "numactl":         None,
    "hwloc":           None,
    "msr-tools":       None,
    "sysstat":         None,
}

# Common Python packages installed into the base conda env.
# Benchmark-specific packages belong in benchmarks/<name>/setup.py.
COMMON_PIP: List[str] = [
    "pyyaml>=6.0",
    "psutil>=5.9",
    "requests>=2.28",
    "tqdm>=4.60",
    "huggingface_hub[cli]>=0.23",
    "pandas>=2.0",
    "numpy>=1.24",
    "rich>=13.0",
    "python-dotenv>=1.0",
]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class Color:
    BLUE   = "\033[94m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"


def log(msg: str, level: str = "info") -> None:
    colors = {"info": Color.BLUE, "ok": Color.GREEN, "warn": Color.YELLOW, "error": Color.RED}
    prefix = {"info": "[INFO]", "ok": "[ OK ]", "warn": "[WARN]", "error": "[ERR ]"}
    c = colors.get(level, "")
    p = prefix.get(level, "[    ]")
    print(f"{c}{Color.BOLD}{p}{Color.RESET}{c} {msg}{Color.RESET}", flush=True)


def banner(title: str) -> None:
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*60}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}  {title}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}{'='*60}{Color.RESET}\n")


def run(cmd: str, dry_run: bool = False, check: bool = True,
        capture: bool = False) -> Optional[subprocess.CompletedProcess]:
    print(f"  $ {cmd}", flush=True)
    if dry_run:
        return None
    result = subprocess.run(
        cmd, shell=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )
    if check and result.returncode != 0:
        log(f"Command failed (exit {result.returncode}): {cmd}", "error")
    return result


def detect_os() -> Dict[str, str]:
    info = {"family": "unknown", "id": "unknown", "version": "0", "pretty": "Unknown"}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ID="):
                    info["id"] = line.split("=", 1)[1].strip('"').lower()
                elif line.startswith("VERSION_ID="):
                    info["version"] = line.split("=", 1)[1].strip('"')
                elif line.startswith("PRETTY_NAME="):
                    info["pretty"] = line.split("=", 1)[1].strip('"')
    except FileNotFoundError:
        pass

    ubuntu_ids = {"ubuntu", "debian", "linuxmint", "pop"}
    centos_ids = {"centos", "rhel", "fedora", "rocky", "almalinux", "ol"}

    if info["id"] in ubuntu_ids:
        info["family"] = "ubuntu"
    elif info["id"] in centos_ids:
        info["family"] = "centos"
    elif shutil.which("apt-get"):
        info["family"] = "ubuntu"
    elif shutil.which("dnf") or shutil.which("yum"):
        info["family"] = "centos"

    return info


# ---------------------------------------------------------------------------
# Step 1: Base system packages
# ---------------------------------------------------------------------------

def _apt_install_resilient(pkgs: List[str], dry_run: bool) -> None:
    """Install packages via apt-get, falling back to one-by-one installs.

    apt-get install fails ATOMICALLY if even one package name can't be
    located — none of the requested packages get installed, not just the
    bad one. Retrying individually isolates the failure so a single typo'd
    or unavailable package name never blocks the rest of the list.
    """
    result = run(f"sudo apt-get install -y {' '.join(pkgs)}", dry_run=dry_run, check=False)
    if dry_run or (result is not None and result.returncode == 0):
        return
    log("Bulk apt install failed — retrying packages individually ...", "warn")
    failed = []
    for pkg in pkgs:
        r = run(f"sudo apt-get install -y {pkg}", dry_run=dry_run, check=False)
        if r is not None and r.returncode != 0:
            failed.append(pkg)
    if failed:
        log(f"Packages unavailable/failed (skipped): {', '.join(failed)}", "warn")


def _dnf_install_resilient(pkgs: List[str], dry_run: bool) -> None:
    """Install packages via dnf/yum, falling back to one-by-one on bulk failure."""
    result = run(f"sudo dnf install -y {' '.join(pkgs)} || sudo yum install -y {' '.join(pkgs)}",
                 dry_run=dry_run, check=False)
    if dry_run or (result is not None and result.returncode == 0):
        return
    log("Bulk dnf/yum install failed — retrying packages individually ...", "warn")
    failed = []
    for pkg in pkgs:
        r = run(f"sudo dnf install -y {pkg} || sudo yum install -y {pkg}", dry_run=dry_run, check=False)
        if r is not None and r.returncode != 0:
            failed.append(pkg)
    if failed:
        log(f"Packages unavailable/failed (skipped): {', '.join(failed)}", "warn")


def install_perf_tools(os_info: Dict[str, str], dry_run: bool) -> None:
    """Install the 'perf' profiler — optional, non-fatal on failure.

    Ubuntu has no 'perf' apt package; it ships inside linux-tools-<kernel>.
    That package name is only valid for the exact running kernel, so on
    minimal/cloud images it can be unavailable — never let that block setup.
    """
    family = os_info["family"]
    if family == "ubuntu":
        run("sudo apt-get install -y linux-tools-common linux-tools-generic "
            "linux-tools-$(uname -r)", dry_run=dry_run, check=False)
    elif family == "centos":
        run("sudo dnf install -y perf || sudo yum install -y perf", dry_run=dry_run, check=False)
    if not dry_run and not shutil.which("perf"):
        log("perf not available (non-fatal) — EMON/SEP does not require it.", "warn")


def install_system_base(os_info: Dict[str, str], dry_run: bool) -> None:
    banner("Step 1: Base System Packages")
    family = os_info["family"]

    if family == "ubuntu":
        run("sudo apt-get update -y", dry_run=dry_run, check=False)
        pkgs = list(BASE_SYSTEM_PKGS.keys())
        _apt_install_resilient(pkgs, dry_run)

    elif family == "centos":
        run("sudo dnf update -y --quiet || sudo yum update -y --quiet",
            dry_run=dry_run, check=False)
        pkgs: List[str] = []
        for ubuntu_pkg, centos_pkg in BASE_SYSTEM_PKGS.items():
            if centos_pkg is None:
                pkgs.append(ubuntu_pkg)
            elif centos_pkg:
                pkgs.extend(centos_pkg.split())
        _dnf_install_resilient(pkgs, dry_run)
    else:
        log(f"Unknown OS family '{family}' — skipping system packages.", "warn")
        return

    install_perf_tools(os_info, dry_run)
    log("Base system packages installed", "ok")


# ---------------------------------------------------------------------------
# Step 2: Docker CE
# ---------------------------------------------------------------------------

def _configure_docker_proxy(dry_run: bool) -> None:
    http_proxy  = os.environ.get("HTTP_PROXY")  or os.environ.get("http_proxy",  "")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy", "")
    no_proxy    = os.environ.get("NO_PROXY")    or os.environ.get("no_proxy",    "")
    if not http_proxy and not https_proxy:
        return
    conf_dir = Path("/etc/systemd/system/docker.service.d")
    if not dry_run:
        try:
            conf_dir.mkdir(parents=True, exist_ok=True)
            (conf_dir / "proxy.conf").write_text(
                "[Service]\n"
                f'Environment="HTTP_PROXY={http_proxy}"\n'
                f'Environment="HTTPS_PROXY={https_proxy}"\n'
                f'Environment="NO_PROXY={no_proxy}"\n'
            )
        except PermissionError:
            log("Could not write Docker proxy config (need sudo) — skipping.", "warn")
            return
    run("sudo systemctl daemon-reload", dry_run=dry_run, check=False)
    run("sudo systemctl restart docker", dry_run=dry_run, check=False)
    log("Docker proxy configured", "ok")


def install_docker(os_info: Dict[str, str], dry_run: bool) -> None:
    banner("Step 2: Docker CE")

    # Load iptables modules (RHEL9 Docker NAT requirement)
    if os_info["family"] == "centos":
        for mod in ("ip_tables", "iptable_nat", "iptable_filter", "ip_conntrack"):
            run(f"modprobe {mod}", dry_run=dry_run, check=False)
        modules_conf = "/etc/modules-load.d/docker-nat.conf"
        if not dry_run:
            try:
                Path(modules_conf).write_text(
                    "ip_tables\niptable_nat\niptable_filter\nip_conntrack\n"
                )
            except PermissionError:
                run(f"echo 'ip_tables\niptable_nat\niptable_filter\nip_conntrack' "
                    f"| sudo tee {modules_conf}", dry_run=dry_run, check=False)

    if shutil.which("docker") and not dry_run:
        log("Docker already installed.", "ok")
        _configure_docker_proxy(dry_run)
        return

    family = os_info["family"]
    if family == "ubuntu":
        script = (
            "sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true\n"
            "sudo apt-get update -y\n"
            "sudo apt-get install -y ca-certificates curl gnupg lsb-release\n"
            "sudo install -m 0755 -d /etc/apt/keyrings\n"
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | "
            "sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg\n"
            "sudo chmod a+r /etc/apt/keyrings/docker.gpg\n"
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] '
            'https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | '
            "sudo tee /etc/apt/sources.list.d/docker.list > /dev/null\n"
            "sudo apt-get update -y\n"
            "sudo apt-get install -y docker-ce docker-ce-cli containerd.io "
            "docker-buildx-plugin docker-compose-plugin\n"
        )
        run(script, dry_run=dry_run, check=False)
    elif family == "centos":
        script = (
            "sudo dnf remove -y docker docker-client docker-client-latest docker-common "
            "docker-latest docker-latest-logrotate docker-logrotate docker-engine 2>/dev/null || true\n"
            "sudo dnf install -y yum-utils\n"
            "sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo\n"
            "sudo dnf install -y docker-ce docker-ce-cli containerd.io "
            "docker-buildx-plugin docker-compose-plugin\n"
        )
        run(script, dry_run=dry_run, check=False)
    else:
        log(f"Unknown OS family '{family}' — skipping Docker.", "warn")
        return

    run("sudo systemctl enable --now docker", dry_run=dry_run, check=False)
    run(f"sudo usermod -aG docker {os.environ.get('USER', 'root')} || true",
        dry_run=dry_run, check=False)
    _configure_docker_proxy(dry_run)
    log("Docker installed and running", "ok")


# ---------------------------------------------------------------------------
# Step 3: Conda environment
# ---------------------------------------------------------------------------

def _is_valid_shell_installer(path: str) -> bool:
    """Return True if `path` looks like a real shell installer, not an HTML
    error/block page (e.g. corp proxy block pages, expired-link landing pages).
    """
    try:
        with open(path, "rb") as _fh:
            head = _fh.read(512)
    except OSError:
        return False
    if not head.startswith(b"#!"):
        return False
    if b"<!DOCTYPE" in head[:64] or b"<html" in head[:64].lower():
        return False
    return True


def _download_file(url: str, dest: str, dry_run: bool) -> bool:
    """Try wget then curl to fetch `url` into `dest`; validate it's a real
    shell script afterwards (not a proxy/CDN HTML block page). Returns True
    on a validated download.
    """
    if shutil.which("wget"):
        run(f"wget --no-check-certificate -q {url} -O {dest}", dry_run=dry_run, check=False)
        if dry_run or _is_valid_shell_installer(dest):
            return True
    if shutil.which("curl"):
        run(f"curl -k -L -f {url} -o {dest}", dry_run=dry_run, check=False)
        if dry_run or _is_valid_shell_installer(dest):
            return True
    return False


def setup_conda(conda_env: str, python_version: str, dry_run: bool) -> None:
    banner(f"Step 3: Conda Environment  [{conda_env}, Python {python_version}]")

    if not shutil.which("conda"):
        log("conda not found — installing Miniconda ...", "info")
        installer = "/tmp/miniconda.sh"
        cached = Path(MINICONDA_LOCAL)
        if cached.exists():
            installer = str(cached)
            log(f"Using cached installer: {cached}", "ok")
        else:
            # NOTE: these are PUBLIC internet URLs, not internal Intel hosts —
            # unlike Artifactory downloads they must go THROUGH the corp proxy
            # (if one is configured via HTTP_PROXY/HTTPS_PROXY env vars), so we
            # deliberately do NOT disable proxying here. --no-check-certificate
            # / -k only bypass corp SSL-inspection certs, they don't touch proxying.
            #
            # Miniforge (GitHub-hosted, BSD-licensed conda-forge installer) is
            # tried FIRST: many corp networks (incl. Intel) block/redirect
            # repo.anaconda.com to an HTML page because of Anaconda's 2020
            # commercial-use ToS change. GitHub is already known-reachable
            # here (used for the TMC client clone below).
            candidate_urls = [
                "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh",
                "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh",
            ]
            downloaded = False
            for url in candidate_urls:
                log(f"Trying installer source: {url}", "info")
                if _download_file(url, installer, dry_run):
                    downloaded = True
                    break
                log(f"Download from {url} did not yield a valid shell script "
                    "(likely blocked/redirected by proxy) — trying next source.", "warn")
            if not downloaded and not dry_run:
                log("All conda installer download sources failed.", "error")
                log(f"Pre-download an installer to {MINICONDA_LOCAL} and rerun, "
                    "or run with --skip-conda.", "error")
                sys.exit(1)
        run(f"bash {installer} -b -p {Path.home()}/miniconda3",
            dry_run=dry_run, check=False)
        # Update PATH immediately so all subsequent conda calls in this process work
        conda_bin = str(Path.home() / "miniconda3" / "bin")
        if not dry_run and not Path(conda_bin, "conda").exists():
            log(f"Miniconda install failed \u2014 {conda_bin}/conda not found after install.", "error")
            log("Check network/proxy access to repo.anaconda.com and retry, or pre-download the "
                f"installer to {MINICONDA_LOCAL} and rerun.", "error")
            sys.exit(1)
        os.environ["PATH"] = conda_bin + ":" + os.environ.get("PATH", "")
        run(f"{conda_bin}/conda init bash", dry_run=dry_run, check=False)
        # Write a one-liner to /etc/profile.d so root's non-interactive shells also get conda
        profile_snippet = Path("/etc/profile.d/conda.sh")
        if not dry_run:
            try:
                profile_snippet.write_text(
                    f". {Path.home()}/miniconda3/etc/profile.d/conda.sh\n"
                )
                log(f"Wrote conda init to {profile_snippet}", "ok")
            except PermissionError:
                pass  # non-root install — ~/.bashrc is sufficient
        print(
            "\n"
            "  ╔══════════════════════════════════════════════════════════╗\n"
            "  ║  ACTION REQUIRED — activate conda in the current shell  ║\n"
            f"  ║  Run:  source ~/.bashrc                                  ║\n"
            f"  ║   or:  source {Path.home()}/miniconda3/etc/profile.d/conda.sh\n"
            "  ║  Then: conda activate agentic                           ║\n"
            "  ╚══════════════════════════════════════════════════════════╝\n",
            flush=True,
        )

    # Use full path so conda works even if not yet in shell PATH
    conda_cmd = str(Path.home() / "miniconda3" / "bin" / "conda")
    if not Path(conda_cmd).exists():
        conda_cmd = shutil.which("conda") or "conda"  # fall back to PATH

    result = subprocess.run(f"{conda_cmd} env list", shell=True, capture_output=True, text=True)
    if not dry_run and conda_env in (result.stdout or ""):
        log(f"Conda env '{conda_env}' already exists.", "ok")
    else:
        run(f"{conda_cmd} create -y -n {conda_env} python={python_version}",
            dry_run=dry_run, check=False)
        log(f"Conda env '{conda_env}' created (Python {python_version})", "ok")


# ---------------------------------------------------------------------------
# Step 4: git-lfs
# ---------------------------------------------------------------------------

def setup_git_lfs(os_info: Dict[str, str], dry_run: bool) -> None:
    banner("Step 4: git-lfs")
    if not (shutil.which("git-lfs") or dry_run):
        # Step 1 should have installed this already; install directly here too
        # so `--skip-system` or a partial Step 1 failure still gets git-lfs.
        log("git-lfs binary not found — installing package ...", "info")
        if os_info["family"] == "ubuntu":
            run("sudo apt-get install -y git-lfs", dry_run=dry_run, check=False)
        elif os_info["family"] == "centos":
            run("sudo dnf install -y git-lfs || sudo yum install -y git-lfs",
                dry_run=dry_run, check=False)

    if not dry_run and not shutil.which("git-lfs"):
        log("git-lfs package install failed — skipping hook setup.", "warn")
        return

    run("git lfs install --system || git lfs install", dry_run=dry_run, check=False)
    log("git-lfs ready", "ok")


# ---------------------------------------------------------------------------
# Step 5: Common Python packages
# ---------------------------------------------------------------------------

def _conda_cmd() -> str:
    """Return full path to conda binary, falling back to 'conda' if already in PATH."""
    full = Path.home() / "miniconda3" / "bin" / "conda"
    if full.exists():
        return str(full)
    return shutil.which("conda") or "conda"


def pip_install(pip_cmd: str, packages: List[str], dry_run: bool) -> None:
    """Install packages idempotently -- pip skips packages already satisfying version constraints."""
    for i in range(0, len(packages), 20):
        chunk = " ".join(f'"{p}"' for p in packages[i:i+20])
        run(f"{pip_cmd} install --quiet {chunk}", dry_run=dry_run, check=False)


def install_common_pip(conda_env: str, dry_run: bool) -> None:
    banner(f"Step 5: Common Python Packages  (conda env: {conda_env})")
    conda = _conda_cmd()
    run(f"{conda} run -n {conda_env} pip install --upgrade pip setuptools wheel",
        dry_run=dry_run, check=False)
    log(f"Installing {len(COMMON_PIP)} packages (skipping already-satisfied)...", "info")
    pip_install(f"{conda} run -n {conda_env} pip", COMMON_PIP, dry_run)
    log("Common Python packages installed", "ok")


# ---------------------------------------------------------------------------
# Step 6: Intel SEP/EMON telemetry stack
# ---------------------------------------------------------------------------

def install_emon(dry_run: bool, sep_installer: str = "",
                 skip_kernel_devel: bool = False) -> None:
    """
    Delegates to setup/setup_emon.py which matches pnpwls/setup/setup_emon.sh:
      kernel-devel => SEP 5.58 beta => pyedp deps => TMC git clone => insmod-sep
    """
    banner("Step 6: Intel SEP/EMON Telemetry Stack")
    setup_emon_script = Path(__file__).resolve().parent.parent / "setup" / "setup_emon.py"

    if not setup_emon_script.exists():
        log(f"setup_emon.py not found: {setup_emon_script}", "error")
        return

    flags = []
    if dry_run:
        flags.append("--dry-run")
    if sep_installer:
        flags.append(f"--sep-installer {sep_installer}")
    if skip_kernel_devel:
        flags.append("--skip-kernel-devel")

    result = run(
        f"{sys.executable} {setup_emon_script} {' '.join(flags)}",
        dry_run=dry_run, check=False,
    )
    if result and result.returncode != 0:
        log("EMON/SEP setup completed with warnings — check output above.", "warn")
    else:
        log("EMON/SEP setup complete.", "ok")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(conda_env: str, os_info: Dict, emon: bool) -> None:
    banner("Common Setup Complete")
    print(f"  OS        : {os_info['pretty']}")
    print(f"  Conda env : {conda_env}")
    print(f"  EMON/SEP  : {'installed' if emon else 'skipped (use --install-emon)'}")
    print()
    print("  Next — run the benchmark-specific setup:")
    print("    python3 benchmarks/webarena/setup.py")
    print("    python3 benchmarks/swe-bench/setup.py")
    print("    python3 benchmarks/osworld/setup.py")
    print("    python3 benchmarks/appworld/setup.py")
    print("    python3 benchmarks/t-bench/setup.py")
    print()
    print("  Verify EMON:")
    print("    python3 misc/check_emon_setup.py")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CWF Agentic AI — Common Infrastructure Setup",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dry-run",    action="store_true",
                        help="Print commands without executing.")
    parser.add_argument("--skip-system", action="store_true",
                        help="Skip apt/dnf base package installation.")
    parser.add_argument("--skip-docker", action="store_true",
                        help="Skip Docker CE installation.")
    parser.add_argument("--skip-conda",  action="store_true",
                        help="Skip conda environment creation.")
    parser.add_argument("--skip-pip",    action="store_true",
                        help="Skip common Python package installation.")
    parser.add_argument("--conda-env",   default=CONDA_ENV_DEFAULT,
                        help="Conda environment name.")
    parser.add_argument("--python-version", default=PYTHON_VERSION_DEFAULT,
                        help="Python version for conda env.")
    parser.add_argument("--install-emon", action="store_true",
                        help="Install Intel SEP/EMON (requires Intel internal network).")
    parser.add_argument("--sep-installer",
                        help="Path to pre-downloaded SEP .tar.bz2 (skips download).")
    parser.add_argument("--skip-kernel-devel", action="store_true",
                        help="With --install-emon: skip kernel-devel install step.")
    parser.add_argument("--list", action="store_true",
                        help="List available setup components and exit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        components = [
            "system    — Base OS packages (git, curl, build tools)",
            "docker    — Docker CE container runtime",
            "conda     — Miniforge conda + Python environment",
            "pip       — Common Python dependencies",
            "emon      — Intel SEP/EMON telemetry (optional)",
        ]
        print("Available setup components:")
        for c in components:
            print(f"  • {c}")
        return

    if platform.system() != "Linux":
        log("This script targets Linux (CentOS/RHEL or Ubuntu).", "warn")

    os_info = detect_os()
    banner("CWF Agentic AI — Common Infrastructure Setup")
    print(f"  OS        : {os_info['pretty']}  [{os_info['family']}]")
    print(f"  Conda env : {args.conda_env}  (Python {args.python_version})")
    print(f"  EMON      : {'yes' if args.install_emon else 'no  (pass --install-emon to enable)'}")
    print(f"  Dry run   : {args.dry_run}")
    print()

    if not args.skip_system:
        install_system_base(os_info, args.dry_run)

    if not args.skip_docker:
        install_docker(os_info, args.dry_run)

    setup_git_lfs(os_info, args.dry_run)

    if not args.skip_conda:
        setup_conda(args.conda_env, args.python_version, args.dry_run)

    if not args.skip_pip:
        install_common_pip(args.conda_env, args.dry_run)

    if args.install_emon:
        install_emon(
            args.dry_run,
            sep_installer=args.sep_installer or "",
            skip_kernel_devel=args.skip_kernel_devel,
        )

    print_summary(args.conda_env, os_info, args.install_emon)
    log("Common setup complete. Run each benchmark's setup.py next.", "ok")


if __name__ == "__main__":
    main()
