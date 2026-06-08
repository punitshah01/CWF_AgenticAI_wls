#!/usr/bin/env python3
"""
setup.py — CWF Agentic AI: Unified Dependency Installer
=========================================================
Installs ALL system and Python dependencies for every benchmark:
  SWE-bench | WebArena | OSWorld | AppWorld | T-Bench

Supports: Ubuntu 20.04 / 22.04 / 24.04 and CentOS/RHEL 8/9 (dnf).

Usage:
  python3 scripts/setup.py                        # install all benchmarks
  python3 scripts/setup.py --benchmarks swebench webarena
  python3 scripts/setup.py --list                 # show what will be installed
  python3 scripts/setup.py --dry-run              # show commands without running
  python3 scripts/setup.py --skip-system          # skip apt/dnf (already done)
  python3 scripts/setup.py --skip-conda           # skip conda env creation
  python3 scripts/setup.py --conda-env myenv      # custom conda env name (default: agentic)
  python3 scripts/setup.py --python-version 3.11  # override Python version

Requirements sourced from upstream repos (visited 2026-06-08):
  SWE-bench  : github.com/SWE-bench/SWE-bench          pyproject.toml
  WebArena   : github.com/web-arena-x/webarena          requirements.txt
  OSWorld    : github.com/xlang-ai/OSWorld               requirements.txt
  AppWorld   : github.com/StonyBrookNLP/appworld         pyproject.toml
  T-Bench    : lightweight mock-server (no public repo); fastapi + uvicorn

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

# ─────────────────────────────────────────────────────────────────────────────
# ── Constants
# ─────────────────────────────────────────────────────────────────────────────

CONDA_ENV_DEFAULT = "agentic"
PYTHON_VERSION_DEFAULT = "3.11"

# Registry — override with --registry or REGISTRY_URL env var.
# When set, Docker images are pulled from <registry>/cwf-agentic/<name>:<tag>
# instead of Docker Hub.  Set to empty string to pull from internet (default).
REGISTRY_URL_DEFAULT = os.environ.get("REGISTRY_URL", "")

# Path to pre-downloaded Miniconda installer (avoids internet if set)
MINICONDA_LOCAL = os.environ.get("MINICONDA_LOCAL", "assets/installers/Miniconda3-latest-Linux-x86_64.sh")

# Minimum Python per benchmark (enforced at runtime, not by conda)
PYTHON_MIN = {
    "swebench": (3, 10),
    "webarena": (3, 10),
    "osworld":  (3, 10),
    "appworld": (3, 11),   # AppWorld hard-requires 3.11+
    "tbench":   (3, 10),
}

# ─────────────────────────────────────────────────────────────────────────────
# ── System package maps: {ubuntu_pkg: centos_pkg}
#    Value None means same name on both distros.
#    Value "" means not available via pkg manager (handled specially).
# ─────────────────────────────────────────────────────────────────────────────

# Packages needed regardless of benchmark selection
BASE_SYSTEM_PKGS: Dict[str, Optional[str]] = {
    "git":                    None,
    "git-lfs":                None,        # git-lfs copr on RHEL if needed
    "curl":                   None,
    "wget":                   None,
    "build-essential":        "gcc gcc-c++ make",
    "cmake":                  None,
    "pkg-config":             "pkgconfig",
    "python3-pip":            "python3-pip",
    "python3-dev":            "python3-devel",
    "htop":                   None,
    "numactl":                None,
    "hwloc":                  None,
    "msr-tools":              None,
}

# Docker (separate install path; CE repo required on both OSes)
DOCKER_PKGS_UBUNTU: List[str] = [
    "ca-certificates", "gnupg", "lsb-release",
    "docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin",
    "docker-compose-plugin",
]
DOCKER_PKGS_CENTOS: List[str] = [
    "yum-utils",
    "docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin",
    "docker-compose-plugin",
]

# KVM / QEMU / libvirt (OSWorld hard requirement)
KVM_PKGS: Dict[str, str] = {
    "ubuntu": "qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virt-manager",
    "centos": "qemu-kvm libvirt libvirt-devel virt-install virt-manager bridge-utils",
}

# Benchmark-specific EXTRA system packages (beyond base)
BENCH_SYSTEM_PKGS: Dict[str, Dict[str, str]] = {
    "swebench": {
        "ubuntu": "docker-ce",   # just ensure Docker; listed separately
        "centos": "docker-ce",
    },
    "webarena": {
        # Playwright needs Chromium system libs
        "ubuntu": (
            "libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 "
            "libcups2 libdrm2 libdbus-1-3 libxcb1 libxkbcommon0 "
            "libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 "
            "libgbm1 libpango-1.0-0 libcairo2 libasound2"
        ),
        "centos": (
            "glib2 nss nspr atk at-spi2-atk cups-libs libdrm dbus-libs "
            "libxcb libxkbcommon libX11 libXcomposite libXdamage libXext "
            "libXfixes libXrandr mesa-libgbm pango cairo alsa-lib"
        ),
    },
    "osworld": {
        # KVM + OpenCV + audio + X11 headless support
        "ubuntu": (
            "qemu-kvm libvirt-daemon-system libvirt-clients "
            "libgl1-mesa-glx libglib2.0-0 libsm6 libxrender1 libxext6 "
            "libgstreamer1.0-0 gstreamer1.0-plugins-good "
            "portaudio19-dev libsndfile1-dev libportmidi-dev "
            "xvfb x11-utils"
        ),
        "centos": (
            "qemu-kvm libvirt libvirt-devel "
            "mesa-libGL glib2 libSM libXrender libXext "
            "gstreamer1 gstreamer1-plugins-good "
            "portaudio-devel libsndfile-devel portmidi-devel "
            "xorg-x11-server-Xvfb x11-utils"
        ),
    },
    "appworld": {
        "ubuntu": "git-lfs libssl-dev",
        "centos": "git-lfs openssl-devel",
    },
    "tbench": {
        "ubuntu": "",  # no system deps beyond base
        "centos": "",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# ── Python package requirements (sourced from upstream repos)
# ─────────────────────────────────────────────────────────────────────────────

# SWE-bench pyproject.toml  [project].dependencies + core extras
# Source: github.com/SWE-bench/SWE-bench/blob/main/pyproject.toml
SWEBENCH_PIP: List[str] = [
    "swebench",        # installs via pip -e . after git clone, but also on PyPI
    # core deps (in case installing without repo)
    "beautifulsoup4",
    "chardet",
    "datasets",
    "docker",
    "ghapi",
    "GitPython",
    "modal",
    "python-dotenv",
    "requests",
    "rich",
    "tenacity",
    "tqdm",
    "unidiff",
    # optional inference/datasets extras
    "protobuf",
    "sentencepiece",
    "tiktoken",
    "transformers",
    "openai",
    "anthropic",
    "jedi",
    "pytest",
    "pytest-cov",
]

# WebArena requirements.txt
# Source: github.com/web-arena-x/webarena/blob/main/requirements.txt
WEBARENA_PIP: List[str] = [
    "gymnasium",
    "playwright==1.32.1",
    "Pillow",
    "evaluate",
    "openai==0.27.0",
    "types-tqdm",
    "tiktoken",
    "aiolimiter",
    "beartype==0.12.0",
    "flask",
    "nltk",
    "text-generation",
    "transformers==4.33.2",
]

# OSWorld requirements.txt (full list)
# Source: github.com/xlang-ai/OSWorld/blob/main/requirements.txt
OSWORLD_PIP: List[str] = [
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
    "PyGetWindow",
    "rapidfuzz",
    "pyacoustid",
    "pygame",
    "ImageHash",
    "scikit-image",
    "librosa",
    "pymupdf",
    "chardet",
    "playwright",
    "backoff",
    "formulas",
    "pydrive",
    "fastdtw",
    "odfpy",
    "openai",
    "func-timeout",
    "beautifulsoup4",
    "PyYAML",
    "mutagen",
    "easyocr",
    "borb<3",
    "pypdf2",
    "pdfplumber",
    "wrapt_timeout_decorator",
    "gdown",
    "tiktoken",
    "groq",
    "boto3",
    "azure-identity",
    "azure-mgmt-compute",
    "azure-mgmt-network",
    "docker",
    "loguru",
    "python-dotenv",
    "tldextract",
    "anthropic",
    "json-minify",
    "json-repair",
    "ui-tars>=0.4.2.2",
    # Cloud SDKs (optional but listed in requirements.txt)
    "google-generativeai",
    "dashscope",
    "wandb",
]

# AppWorld pyproject.toml [project].dependencies
# Source: github.com/StonyBrookNLP/appworld/blob/main/pyproject.toml
# (installs via `pip install appworld && appworld install` — but listing core deps)
APPWORLD_PIP: List[str] = [
    "appworld",      # installs the full package from PyPI
    # core framework deps (already pulled by `appworld` package, listed for clarity)
    "fastapi>=0.110",
    "fastapi-login>=1.10.2",
    "sqlmodel>=0.0.19",
    "pydantic>=2.12.0",
    "sqlalchemy-utils>=0.41.1",
    "pendulum>=3.0.0",
    "freezegun>=1.5.0,<=1.5.1",
    "uvicorn>=0.27",
    "ipython>=8.18.0",
    "typer>=0.16.0",
    "text2num>=0.3.0",
    "orjson>=3.10.12",
    "pydantic-extra-types[pendulum]>=2.8.0",
    "requests>=2.28.0",
    "inflection>=0.5.1",
    "email-validator>=2.0.0",
    "polyfactory>=2.15.0",
    "faker>=18.0.0",
    "xxhash>=3.0.0",
    "munch>=4.0.0",
    "rich>=13.0.0",
    "tqdm>=4.60.0",
    "python-dotenv>=1.0.1",
    "cryptography>=44.0.0",
    "python-multipart>=0.0.5",
    "httpx>=0.20.0",
    "libcst>=1.2.0",
    "typing-extensions>=4.12.2",
    "pyyaml>=6.0.1",
    "psutil>=5.9.0",
    "jsonref>=1.1.0",
    "filelock>=3.1.0",
    "uvloop>=0.21.0",   # Linux/macOS only
]

# T-Bench — no public GitHub repo; lightweight mock REST API + evaluation harness
# Deps: fastapi server + requests client + evaluation utils
TBENCH_PIP: List[str] = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "requests>=2.28.0",
    "jsonschema>=4.19.0",
    "pydantic>=2.12.0",
    "rich>=13.0.0",
    "tqdm>=4.60.0",
    "python-dotenv>=1.0.1",
    "httpx>=0.20.0",
    "pytest>=7.0.0",
]

# Common inference stack (shared across all benchmarks)
INFERENCE_PIP: List[str] = [
    "vllm",           # vLLM with CPU/OpenVINO backend
    "huggingface_hub",
    "accelerate",
    "sentencepiece",
    "tokenizers",
]

# Consolidated map
BENCH_PIP: Dict[str, List[str]] = {
    "swebench": SWEBENCH_PIP,
    "webarena": WEBARENA_PIP,
    "osworld":  OSWORLD_PIP,
    "appworld": APPWORLD_PIP,
    "tbench":   TBENCH_PIP,
}

ALL_BENCHMARKS = list(BENCH_PIP.keys())

# ─────────────────────────────────────────────────────────────────────────────
# ── Utilities
# ─────────────────────────────────────────────────────────────────────────────

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
        if capture:
            print(result.stderr or result.stdout or "")
    return result

def detect_os() -> Dict[str, str]:
    """Detect OS family, id, and version."""
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

def check_kvm() -> bool:
    try:
        result = subprocess.run(
            "egrep -c '(vmx|svm)' /proc/cpuinfo",
            shell=True, capture_output=True, text=True
        )
        return int(result.stdout.strip()) > 0
    except Exception:
        return False

def get_conda_python(env_name: str) -> Optional[str]:
    """Return path to python in a conda env, if it exists."""
    result = subprocess.run(
        f"conda run -n {env_name} which python",
        shell=True, capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None

def pip_install(packages: List[str], conda_env: str, dry_run: bool,
                extra_index: str = "", pip_cache_dir: str = "") -> None:
    """Install a list of pip packages in the given conda env."""
    if not packages:
        return
    idx_flag = f"--extra-index-url {extra_index}" if extra_index else ""
    cache_flag = f"--cache-dir {pip_cache_dir}" if pip_cache_dir else ""
    # Chunk into groups of 20 to avoid very long command lines
    chunk_size = 20
    for i in range(0, len(packages), chunk_size):
        chunk = packages[i:i + chunk_size]
        pkg_str = " ".join(f'"{p}"' for p in chunk)
        cmd = f'conda run -n {conda_env} pip install --quiet {cache_flag} {idx_flag} {pkg_str}'
        run(cmd, dry_run=dry_run, check=False)

# ─────────────────────────────────────────────────────────────────────────────
# ── Step 1: System packages
# ─────────────────────────────────────────────────────────────────────────────

def install_system_base(os_info: Dict[str, str], dry_run: bool) -> None:
    banner("Step 1: Base System Packages")
    family = os_info["family"]

    if family == "ubuntu":
        run("sudo apt-get update -y", dry_run=dry_run, check=False)
        pkgs = []
        for ubuntu_pkg in BASE_SYSTEM_PKGS:
            pkgs.append(ubuntu_pkg)
        run(f"sudo apt-get install -y {' '.join(pkgs)}", dry_run=dry_run, check=False)
        log("Base Ubuntu packages installed", "ok")

    elif family == "centos":
        run("sudo dnf update -y --quiet || sudo yum update -y --quiet",
            dry_run=dry_run, check=False)
        pkgs = []
        for ubuntu_pkg, centos_pkg in BASE_SYSTEM_PKGS.items():
            if centos_pkg is None:
                pkgs.append(ubuntu_pkg)
            elif centos_pkg:
                pkgs.extend(centos_pkg.split())
        run(f"sudo dnf install -y {' '.join(pkgs)} || sudo yum install -y {' '.join(pkgs)}",
            dry_run=dry_run, check=False)
        log("Base CentOS/RHEL packages installed", "ok")
    else:
        log(f"Unknown OS family: {family}. Skipping system packages.", "warn")


def install_docker(os_info: Dict[str, str], dry_run: bool) -> None:
    banner("Step 2: Docker CE")

    if shutil.which("docker") and not dry_run:
        log("Docker already installed, skipping.", "ok")
        return

    family = os_info["family"]

    if family == "ubuntu":
        script = """
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
"""
        run(script, dry_run=dry_run, check=False)

    elif family == "centos":
        script = """
sudo dnf remove -y docker docker-client docker-client-latest docker-common \
    docker-latest docker-latest-logrotate docker-logrotate docker-engine 2>/dev/null || true
sudo dnf install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
"""
        run(script, dry_run=dry_run, check=False)

    run("sudo systemctl enable --now docker", dry_run=dry_run, check=False)
    run(f"sudo usermod -aG docker {os.environ.get('USER', 'root')} || true",
        dry_run=dry_run, check=False)
    run("docker run --rm hello-world", dry_run=dry_run, check=False)
    log("Docker installed and running", "ok")


def install_kvm(os_info: Dict[str, str], dry_run: bool) -> None:
    banner("Step 3: KVM / QEMU / libvirt  (OSWorld requirement)")

    if not check_kvm():
        log("KVM flags (vmx/svm) not found in /proc/cpuinfo.", "warn")
        log("OSWorld will NOT work. Enable VT-x in BIOS.", "warn")

    family = os_info["family"]
    pkgs = KVM_PKGS.get(family, "")
    if not pkgs:
        log(f"Unknown OS family {family}, skipping KVM packages.", "warn")
        return

    if family == "ubuntu":
        run(f"sudo apt-get install -y {pkgs}", dry_run=dry_run, check=False)
    else:
        run(f"sudo dnf install -y {pkgs} || sudo yum install -y {pkgs}",
            dry_run=dry_run, check=False)

    run("sudo systemctl enable --now libvirtd", dry_run=dry_run, check=False)

    # Enable nested virtualization for Intel
    run("sudo modprobe kvm_intel nested=1 || true", dry_run=dry_run, check=False)
    if not dry_run:
        nested_conf = "/etc/modprobe.d/kvm-intel.conf"
        try:
            Path(nested_conf).write_text("options kvm-intel nested=1\n")
            log(f"Nested virt configured in {nested_conf}", "ok")
        except PermissionError:
            run(f"echo 'options kvm-intel nested=1' | sudo tee {nested_conf}",
                dry_run=dry_run, check=False)

    log("KVM/libvirt installed", "ok")


def install_bench_system_pkgs(bench: str, os_info: Dict[str, str],
                               dry_run: bool) -> None:
    """Install benchmark-specific system packages."""
    family = os_info["family"]
    pkgs = BENCH_SYSTEM_PKGS.get(bench, {}).get(family, "")
    if not pkgs:
        return
    log(f"  [{bench}] Installing system packages: {pkgs[:60]}...", "info")
    if family == "ubuntu":
        run(f"sudo apt-get install -y {pkgs}", dry_run=dry_run, check=False)
    else:
        run(f"sudo dnf install -y {pkgs} || sudo yum install -y {pkgs}",
            dry_run=dry_run, check=False)


# ─────────────────────────────────────────────────────────────────────────────
# ── Step 2: Conda environment
# ─────────────────────────────────────────────────────────────────────────────

def setup_conda(conda_env: str, python_version: str, dry_run: bool) -> str:
    """Create / reuse conda env. Returns env name."""
    banner(f"Step 4: Conda Environment  [{conda_env}, Python {python_version}]")

    if not shutil.which("conda"):
        log("conda not found. Installing Miniconda...", "info")
        miniconda_url = "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
        home = Path.home()
        installer = "/tmp/miniconda.sh"
        # Use cached installer if available (pre-fetched by prefetch_assets.py)
        cached = Path(MINICONDA_LOCAL)
        if cached.exists():
            log(f"Using cached Miniconda installer: {cached}", "ok")
            installer = str(cached)
        else:
            run(f"wget -q {miniconda_url} -O {installer}", dry_run=dry_run, check=False)
        run(f"bash {installer} -b -p {home}/miniconda3", dry_run=dry_run, check=False)
        run(f"{home}/miniconda3/bin/conda init bash", dry_run=dry_run, check=False)
        os.environ["PATH"] = f"{home}/miniconda3/bin:" + os.environ.get("PATH", "")
        log("Miniconda installed. Restart shell or source ~/.bashrc after setup.", "warn")

    # Check if env already exists
    result = subprocess.run("conda env list", shell=True, capture_output=True, text=True)
    if not dry_run and conda_env in (result.stdout or ""):
        log(f"Conda env '{conda_env}' already exists — using it.", "ok")
    else:
        run(f"conda create -y -n {conda_env} python={python_version}",
            dry_run=dry_run, check=False)
        log(f"Conda env '{conda_env}' created with Python {python_version}", "ok")

    return conda_env


# ─────────────────────────────────────────────────────────────────────────────
# ── Step 3: git-lfs (required by AppWorld)
# ─────────────────────────────────────────────────────────────────────────────

def setup_git_lfs(dry_run: bool) -> None:
    banner("Step 5: git-lfs")
    if shutil.which("git-lfs") and not dry_run:
        log("git-lfs already installed.", "ok")
    else:
        run("git lfs install --system || git lfs install", dry_run=dry_run, check=False)
    log("git-lfs ready", "ok")


# ─────────────────────────────────────────────────────────────────────────────
# ── Step 4: Playwright browser (SWE-bench, WebArena, OSWorld)
# ─────────────────────────────────────────────────────────────────────────────

def setup_playwright(conda_env: str, dry_run: bool) -> None:
    banner("Step 6: Playwright Chromium")
    run(f"conda run -n {conda_env} playwright install chromium",
        dry_run=dry_run, check=False)
    run(f"conda run -n {conda_env} playwright install-deps chromium",
        dry_run=dry_run, check=False)
    log("Playwright Chromium installed", "ok")


# ─────────────────────────────────────────────────────────────────────────────
# ── Step 5: Python packages per benchmark
# ─────────────────────────────────────────────────────────────────────────────

def install_python_packages(benchmarks: List[str], conda_env: str,
                             dry_run: bool, pip_cache_dir: str = "") -> None:
    banner(f"Step 7: Python Packages  (conda env: {conda_env})")

    # Set PIP_CACHE_DIR in environment for all sub-calls
    if pip_cache_dir:
        os.environ["PIP_CACHE_DIR"] = pip_cache_dir
        log(f"pip cache dir: {pip_cache_dir}", "info")

    # Upgrade pip first
    run(f"conda run -n {conda_env} pip install --upgrade pip setuptools wheel",
        dry_run=dry_run, check=False)

    # Torch CPU (CWF: no GPU — explicit CPU-only to avoid downloading CUDA wheels)
    log("Installing PyTorch (CPU-only, for CWF E-core)...", "info")
    cache_flag = f"--cache-dir {pip_cache_dir}" if pip_cache_dir else ""
    run(
        f'conda run -n {conda_env} pip install --quiet {cache_flag} '
        f'"torch>=2.5.0" torchvision torchaudio '
        f'--index-url https://download.pytorch.org/whl/cpu',
        dry_run=dry_run, check=False
    )

    # Benchmark-specific packages
    installed: set = set()

    for bench in benchmarks:
        pkgs = BENCH_PIP.get(bench, [])
        if not pkgs:
            log(f"  [{bench}] No Python packages defined.", "warn")
            continue

        log(f"  [{bench}] Installing {len(pkgs)} packages...", "info")

        # Deduplicate against already-installed in this run
        new_pkgs = [p for p in pkgs if p.split(">=")[0].split("==")[0].split("~=")[0].split("<")[0].strip().lower() not in installed]
        installed.update(p.split(">=")[0].split("==")[0].split("~=")[0].split("<")[0].strip().lower() for p in pkgs)

        pip_install(new_pkgs, conda_env, dry_run, pip_cache_dir=pip_cache_dir)
        log(f"  [{bench}] Python packages done", "ok")

    # Common inference stack (always installed)
    log("  [inference] Installing vLLM + HuggingFace stack...", "info")
    pip_install(INFERENCE_PIP, conda_env, dry_run, pip_cache_dir=pip_cache_dir)
    log("  [inference] Done", "ok")


# ─────────────────────────────────────────────────────────────────────────────
# ── Step 5b: Pre-pull Docker images from local registry / artifactory
# ─────────────────────────────────────────────────────────────────────────────

# Maps benchmark → list of (source_image, tag) tuples needed at runtime.
# These are the images actually USED when the benchmark runs (not build images).
_BENCH_RUNTIME_IMAGES: Dict[str, List] = {
    "swebench": [
        ("swebench/sweb.base.x86_64", "latest"),
        ("swebench/sweb.eval.x86_64.sympy__sympy", "latest"),
    ],
    "webarena": [
        ("webarena/shopping",       "latest"),
        ("webarena/shopping_admin", "latest"),
        ("webarena/forum",          "latest"),
        ("webarena/gitlab",         "latest"),
        ("webarena/wikipedia",      "latest"),
        ("webarena/map",            "latest"),
    ],
    "osworld": [
        ("xlangai/ubuntu_osworld", "latest"),
    ],
    "appworld": [],
    "tbench":   [],
}


def prefetch_docker_images(benchmarks: List[str], registry: str,
                           namespace: str, dry_run: bool) -> None:
    """
    Pull runtime Docker images.  If ``registry`` is set, images are pulled
    from  <registry>/<namespace>/<basename>:<tag>  (local/artifactory cache)
    instead of Docker Hub.  Falls back to Docker Hub on pull failure.
    """
    if not shutil.which("docker"):
        log("docker not found — skipping image pre-pull", "warn")
        return

    all_images: List = []
    for bench in benchmarks:
        all_images.extend(_BENCH_RUNTIME_IMAGES.get(bench, []))

    if not all_images:
        return

    banner(f"Pre-pulling {len(all_images)} Docker images")
    if registry:
        log(f"Using registry: {registry}/{namespace}", "info")
    else:
        log("No --registry set — pulling directly from Docker Hub", "info")

    for source, tag in all_images:
        basename = source.split("/")[-1]
        if registry:
            # Try registry first
            target = f"{registry}/{namespace}/{basename}:{tag}"
            log(f"  Pulling {target} ...", "info")
            result = run(f"docker pull {target}", dry_run=dry_run, check=False)
            if result and result.returncode == 0:
                # Re-tag to the bare name so workload scripts find it
                run(f"docker tag {target} {source}:{tag}",
                    dry_run=dry_run, check=False)
                log(f"  {source}:{tag} → OK (from registry)", "ok")
                continue
            log(f"  Registry pull failed for {target}; falling back to Docker Hub",
                "warn")
        # Direct Docker Hub pull (or fallback)
        run(f"docker pull {source}:{tag}", dry_run=dry_run, check=False)
        log(f"  {source}:{tag} → OK", "ok")


# ─────────────────────────────────────────────────────────────────────────────
# ── Step 6: Post-install — AppWorld data download
# ─────────────────────────────────────────────────────────────────────────────

def post_install_appworld(conda_env: str, dry_run: bool) -> None:
    banner("Step 8: AppWorld Post-Install  (install + download data)")
    log("Running: appworld install  (~2-3 min, unpacks encrypted bundles)", "info")
    run(f"conda run -n {conda_env} appworld install", dry_run=dry_run, check=False)
    log("Running: appworld download data", "info")
    run(f"conda run -n {conda_env} appworld download data", dry_run=dry_run, check=False)
    log("Running: appworld verify tests", "info")
    run(f"conda run -n {conda_env} appworld verify tests", dry_run=dry_run, check=False)
    log("AppWorld ready", "ok")


def post_install_swebench(conda_env: str, dry_run: bool) -> None:
    banner("Step 8b: SWE-bench Validation  (gold patch on 1 task)")
    log("Cloning SWE-bench if not present...", "info")
    workdir = Path.home() / "cwf_agentic" / "swebench"
    if not workdir.exists() or dry_run:
        run(f"git clone https://github.com/SWE-bench/SWE-bench.git {workdir}",
            dry_run=dry_run, check=False)
        run(f"conda run -n {conda_env} pip install -e {workdir}",
            dry_run=dry_run, check=False)
    log("SWE-bench: running gold-patch validation (1 task)...", "info")
    run(
        f"conda run -n {conda_env} python -m swebench.harness.run_evaluation "
        f"--predictions_path gold --max_workers 1 "
        f"--instance_ids sympy__sympy-20590 --run_id cwf_validate",
        dry_run=dry_run, check=False,
    )
    log("SWE-bench validation done", "ok")


# ─────────────────────────────────────────────────────────────────────────────
# ── Summary
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(benchmarks: List[str], conda_env: str, os_info: Dict) -> None:
    banner("Installation Summary")
    print(f"  OS      : {os_info['pretty']}")
    print(f"  Conda   : {conda_env}")
    print(f"  Benches : {', '.join(benchmarks)}")
    print()
    print("  Next steps:")
    print(f"  1. conda activate {conda_env}")
    print("  2. Start LLM server:")
    print("       bash scripts/inference/start_llamacpp.sh --model 8b --cores 64")
    print("  3. Run a benchmark:")
    print("       conda run -n agentic appworld verify tasks   # AppWorld")
    print("       python -m swebench.harness.run_evaluation --predictions_path gold \\")
    print("           --max_workers 1 --instance_ids sympy__sympy-20590 --run_id val")
    print()
    print("  See benchmarks/<name>/README.md for per-benchmark quick-start.")
    print()


def print_list() -> None:
    banner("Benchmark Package List")
    for bench, pkgs in BENCH_PIP.items():
        min_py = ".".join(str(v) for v in PYTHON_MIN[bench])
        print(f"\n  {Color.BOLD}{bench.upper()}{Color.RESET}  (Python >= {min_py})")
        for p in pkgs:
            print(f"    • {p}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# ── Main
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CWF Agentic AI — Unified Dependency Installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--benchmarks", nargs="+", choices=ALL_BENCHMARKS,
        default=ALL_BENCHMARKS,
        help=f"Benchmarks to install. Default: all. Choices: {ALL_BENCHMARKS}",
    )
    parser.add_argument("--list", action="store_true",
                        help="List all packages that will be installed and exit.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing them.")
    parser.add_argument("--skip-system", action="store_true",
                        help="Skip apt-get / dnf system package installation.")
    parser.add_argument("--skip-docker", action="store_true",
                        help="Skip Docker installation.")
    parser.add_argument("--skip-kvm", action="store_true",
                        help="Skip KVM/QEMU installation (skip if not running OSWorld).")
    parser.add_argument("--skip-conda", action="store_true",
                        help="Skip conda environment creation (use existing).")
    parser.add_argument("--skip-python", action="store_true",
                        help="Skip Python package installation.")
    parser.add_argument("--skip-post-install", action="store_true",
                        help="Skip post-install steps (AppWorld data download, "
                             "SWE-bench validation).")
    parser.add_argument("--conda-env", default=CONDA_ENV_DEFAULT,
                        help=f"Conda environment name. Default: {CONDA_ENV_DEFAULT}")
    parser.add_argument("--python-version", default=PYTHON_VERSION_DEFAULT,
                        help=f"Python version for conda env. Default: {PYTHON_VERSION_DEFAULT}")
    parser.add_argument(
        "--registry", default=REGISTRY_URL_DEFAULT,
        help=(
            "Docker registry URL for pre-pulling images without internet access. "
            "Example: localhost:5000  or  ubit-artifactory-or.intel.com/docker-local. "
            f"Override with REGISTRY_URL env var.  Default: '{REGISTRY_URL_DEFAULT or '(Docker Hub)'}'"
        ),
    )
    parser.add_argument(
        "--registry-namespace", default="cwf-agentic",
        help="Namespace/path prefix inside the registry. Default: cwf-agentic",
    )
    parser.add_argument(
        "--skip-image-pull", action="store_true",
        help="Skip pre-pulling Docker images (useful if images are already cached)",
    )
    parser.add_argument(
        "--pip-cache-dir", default=os.environ.get("PIP_CACHE_DIR", ""),
        help="Path to pip wheel cache directory. Shared cache avoids re-downloading "
             "wheels on each run. Override with PIP_CACHE_DIR env var.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print_list()
        sys.exit(0)

    if platform.system() != "Linux":
        log("This script targets Linux (Ubuntu / CentOS / RHEL).", "warn")
        log("Proceeding anyway — some steps may fail on non-Linux.", "warn")

    os_info = detect_os()
    banner("CWF Agentic AI — Unified Dependency Installer")
    print(f"  OS       : {os_info['pretty']}  [{os_info['family']}]")
    print(f"  Benchmarks: {', '.join(args.benchmarks)}")
    print(f"  Conda env : {args.conda_env}  (Python {args.python_version})")
    print(f"  Registry : {args.registry or '(Docker Hub — internet)'}")
    print(f"  pip cache: {args.pip_cache_dir or '(default)'}")
    print(f"  Dry run  : {args.dry_run}")
    print()

    # ── System packages
    if not args.skip_system:
        install_system_base(os_info, args.dry_run)

    if not args.skip_docker:
        install_docker(os_info, args.dry_run)

    # KVM only if osworld is being installed
    if "osworld" in args.benchmarks and not args.skip_kvm:
        install_kvm(os_info, args.dry_run)

    # Benchmark-specific system packages
    if not args.skip_system:
        for bench in args.benchmarks:
            install_bench_system_pkgs(bench, os_info, args.dry_run)

    setup_git_lfs(args.dry_run)

    # ── Conda environment
    if not args.skip_conda:
        # AppWorld requires >= 3.11; use max of all selected min versions
        required_major = max(PYTHON_MIN[b][0] for b in args.benchmarks)
        required_minor = max(
            PYTHON_MIN[b][1] for b in args.benchmarks
            if PYTHON_MIN[b][0] == required_major
        )
        requested = tuple(int(x) for x in args.python_version.split("."))
        effective_version = args.python_version
        if requested < (required_major, required_minor):
            effective_version = f"{required_major}.{required_minor}"
            log(f"Bumping Python version to {effective_version} "
                f"(required by selected benchmarks).", "warn")
        setup_conda(args.conda_env, effective_version, args.dry_run)

    # ── Playwright (needed by webarena and osworld)
    if any(b in args.benchmarks for b in ("webarena", "osworld", "swebench")):
        setup_playwright(args.conda_env, args.dry_run)

    # ── Pre-pull Docker images from registry (offline-safe)
    if not args.skip_image_pull:
        prefetch_docker_images(
            args.benchmarks, args.registry,
            args.registry_namespace, args.dry_run,
        )

    # ── Python packages
    if not args.skip_python:
        install_python_packages(args.benchmarks, args.conda_env, args.dry_run,
                                pip_cache_dir=args.pip_cache_dir)

    # ── Post-install
    if not args.skip_post_install:
        if "appworld" in args.benchmarks:
            post_install_appworld(args.conda_env, args.dry_run)
        if "swebench" in args.benchmarks:
            post_install_swebench(args.conda_env, args.dry_run)

    print_summary(args.benchmarks, args.conda_env, os_info)
    log("Setup complete.", "ok")


if __name__ == "__main__":
    main()
