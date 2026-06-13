#!/usr/bin/env python3
"""
benchmarks/osworld/setup.py - Self-contained OSWorld setup for CWF.

Steps:
  1. Verify KVM / VT-x support (required -- enable in BIOS if missing)
  2. Install KVM + QEMU + libvirt system packages
  3. Install OSWorld system libs (OpenCV, audio, X11, Playwright deps)
  4. Create / reuse conda env (Python 3.10+)
  5. Install OSWorld Python packages (idempotent -- skips if already satisfied)
  6. Clone github.com/xlang-ai/OSWorld

Usage:
  python3 benchmarks/osworld/setup.py
  python3 benchmarks/osworld/setup.py --dry-run
  python3 benchmarks/osworld/setup.py --skip-kvm
  python3 benchmarks/osworld/setup.py --conda-env myenv
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

if sys.version_info < (3, 10):
    sys.exit(f"[ERROR] Python 3.10+ required. Current: {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKDIR   = Path.home() / "cwf_agentic" / "osworld"
CONDA_ENV = "agentic"

PACKAGES: List[str] = [
    "numpy~=1.26.0",
    "Pillow~=11.0.0",
    "fabric",
    "gymnasium~=0.28.1",
    "requests",
    "pytz~=2024.1",
    "transformers~=4.35.2",
    "torch~=2.5.0",
    "accelerate",
    "opencv-python-headless~=4.8.1.78",
    "matplotlib~=3.7.4",
    "pynput~=1.7.6",
    "pyautogui~=0.9.54",
    "psutil~=5.9.6",
    "tqdm~=4.65.0",
    "pandas~=2.2.3",
    "flask~=3.0.0",
    "requests-toolbelt~=1.0.0",
    "ag2~=0.9.7",
    "filelock",
    "lxml",
    "cssselect",
    "xmltodict",
    "openpyxl",
    "python-docx",
    "python-pptx",
    "pypdf",
    "rapidfuzz",
    "pygame",
    "ImageHash",
    "scikit-image",
    "librosa",
    "pymupdf",
    "chardet",
    "playwright",
    "backoff",
    "openai",
    "func-timeout",
    "beautifulsoup4",
    "PyYAML",
    "tiktoken",
    "boto3",
    "docker",
    "loguru",
    "python-dotenv",
    "anthropic",
    "json-repair",
    "gdown",
    "wandb",
]

KVM_PKGS = {
    "centos": "qemu-kvm libvirt libvirt-devel virt-install bridge-utils",
    "ubuntu": "qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils",
}
SYSTEM_PKGS = {
    "centos": (
        "mesa-libGL glib2 libSM libXrender libXext "
        "gstreamer1 gstreamer1-plugins-good portaudio-devel libsndfile-devel "
        "xorg-x11-server-Xvfb"
    ),
    "ubuntu": (
        "libgl1-mesa-glx libglib2.0-0 libsm6 libxrender1 libxext6 "
        "libgstreamer1.0-0 gstreamer1.0-plugins-good portaudio19-dev "
        "libsndfile1-dev xvfb"
    ),
}

# ---------------------------------------------------------------------------

class Color:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def log(msg: str, level: str = "info") -> None:
    c = {"info": Color.BLUE, "ok": Color.GREEN, "warn": Color.YELLOW, "error": Color.RED}.get(level, "")
    p = {"info": "[INFO]", "ok": "[ OK ]", "warn": "[WARN]", "error": "[ERR ]"}.get(level, "")
    print(f"{c}{Color.BOLD}{p}{Color.RESET}{c} {msg}{Color.RESET}", flush=True)

def banner(t: str) -> None:
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*60}\n  {t}\n{'='*60}{Color.RESET}\n")

def run(cmd: str, dry_run: bool = False, check: bool = False) -> Optional[subprocess.CompletedProcess]:
    print(f"  $ {cmd}", flush=True)
    if dry_run:
        return None
    return subprocess.run(cmd, shell=True)

def pip_install(pip_bin: str, packages: List[str], dry_run: bool) -> None:
    """Install packages idempotently -- pip skips packages already satisfying version constraints."""
    for i in range(0, len(packages), 20):
        chunk = " ".join(f'"{p}"' for p in packages[i:i+20])
        run(f"{pip_bin} install --quiet {chunk}", dry_run=dry_run)

def detect_os_family() -> str:
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("ID="):
                os_id = line.split("=", 1)[1].strip('"').lower()
                if os_id in {"centos", "rhel", "fedora", "rocky", "almalinux"}:
                    return "centos"
                if os_id in {"ubuntu", "debian"}:
                    return "ubuntu"
    except OSError:
        pass
    return "centos" if shutil.which("dnf") or shutil.which("yum") else "ubuntu"

def get_conda_pip(conda_env: str) -> str:
    r = subprocess.run(f"conda run -n {conda_env} which pip",
                       shell=True, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "pip"

# ---------------------------------------------------------------------------

def check_kvm() -> bool:
    try:
        return "vmx" in Path("/proc/cpuinfo").read_text()
    except OSError:
        return False

def install_system_pkgs(os_family: str, dry_run: bool) -> None:
    banner("Step 2: System Packages (KVM + OSWorld libs)")
    pm = "dnf" if os_family == "centos" else "apt-get"
    kvm = KVM_PKGS.get(os_family, "")
    sys_libs = SYSTEM_PKGS.get(os_family, "")
    if os_family == "centos":
        run(f"sudo {pm} install -y {kvm} {sys_libs}", dry_run=dry_run)
        run("sudo systemctl enable --now libvirtd", dry_run=dry_run)
    else:
        run("sudo apt-get update -y", dry_run=dry_run)
        run(f"sudo {pm} install -y {kvm} {sys_libs}", dry_run=dry_run)
    log("System packages installed", "ok")

def setup_conda_env(conda_env: str, python_version: str, dry_run: bool) -> None:
    banner("Step 3: Conda Environment")
    if not shutil.which("conda"):
        log("conda not found -- run scripts/setup.py first", "error")
        sys.exit(1)
    result = subprocess.run("conda env list", shell=True, capture_output=True, text=True)
    if not dry_run and conda_env in (result.stdout or ""):
        log(f"Conda env '{conda_env}' already exists.", "ok")
    else:
        run(f"conda create -y -n {conda_env} python={python_version}", dry_run=dry_run)
        log(f"Conda env '{conda_env}' created", "ok")

def install_packages(conda_env: str, dry_run: bool) -> None:
    banner("Step 4: OSWorld Python Packages")
    pip = get_conda_pip(conda_env)
    run(f"{pip} install --upgrade pip setuptools wheel", dry_run=dry_run)
    log(f"Installing {len(PACKAGES)} packages (skipping already-satisfied)...", "info")
    pip_install(pip, PACKAGES, dry_run)
    run(f"conda run -n {conda_env} playwright install chromium", dry_run=dry_run)
    log("Python packages done", "ok")

def clone_osworld(dry_run: bool) -> None:
    banner("Step 5: Clone OSWorld Repository")
    if not dry_run and WORKDIR.exists() and (WORKDIR / "run.py").exists():
        log(f"OSWorld already cloned at {WORKDIR}", "ok")
        return
    WORKDIR.parent.mkdir(parents=True, exist_ok=True)
    run(f"git clone https://github.com/xlang-ai/OSWorld.git {WORKDIR}", dry_run=dry_run)
    log("OSWorld cloned", "ok")

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OSWorld setup for CWF",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--dry-run",        action="store_true")
    p.add_argument("--skip-kvm",       action="store_true", help="Skip KVM check/install")
    p.add_argument("--conda-env",      default=CONDA_ENV)
    p.add_argument("--python-version", default="3.10")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    os_family = detect_os_family()
    banner("OSWorld Setup for CWF")

    if not args.skip_kvm:
        if check_kvm():
            log("KVM flags present in /proc/cpuinfo", "ok")
        else:
            log("KVM flags NOT found -- OSWorld requires KVM. Enable VT-x in BIOS.", "warn")
        install_system_pkgs(os_family, args.dry_run)

    setup_conda_env(args.conda_env, args.python_version, args.dry_run)
    install_packages(args.conda_env, args.dry_run)
    clone_osworld(args.dry_run)
    log("OSWorld setup complete.", "ok")
    if not args.dry_run:
        setup_marker = Path(__file__).resolve().parent / ".setup_complete"
        setup_marker.write_text(f"OSWorld setup completed successfully\nconda_env: {args.conda_env}\n")
        log(f"Setup marker written: {setup_marker}", "ok")
    print(f"\n  Next: conda activate {args.conda_env}")
    print( "        python3 benchmarks/osworld/run.py")
    print("\n[SUCCESS] OSWorld setup complete")
    sys.exit(0)

if __name__ == "__main__":
    main()
