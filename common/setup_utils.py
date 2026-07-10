"""
common/setup_utils.py — Shared helpers for all `setup.py` scripts
===================================================================
This module is the single home for console/formatting and process
helpers that every benchmark's `benchmarks/<name>/setup.py` needs
(colored logging, banners, shell command execution, pip installs,
conda environment management, and setup-completion markers).

Goal: benchmark setup scripts should contain ONLY workload-specific
logic (container setup, task data generation, benchmark environment
validation). Anything generic belongs here so it is written once and
reused by every workload — including future ones.

This module intentionally has **zero third-party dependencies** so it
can be imported by `scripts/setup.py` (which may run under the system
Python before any conda/venv environment exists) as well as by every
`benchmarks/<name>/setup.py`.

Typical usage in a benchmark setup script:

    import sys
    from pathlib import Path

    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(REPO_ROOT))

    from common.setup_utils import (
        Color, log, banner, run, pip_install, get_conda_pip,
        ensure_conda_env, write_setup_marker, require_python_version,
    )
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence


class Color:
    """ANSI color codes for console output."""

    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


_LEVEL_COLOR = {"info": Color.BLUE, "ok": Color.GREEN, "warn": Color.YELLOW, "error": Color.RED}
_LEVEL_PREFIX = {"info": "[INFO]", "ok": "[ OK ]", "warn": "[WARN]", "error": "[ERR ]"}


def log(msg: str, level: str = "info") -> None:
    """Print a colored, leveled log line (info/ok/warn/error)."""
    c = _LEVEL_COLOR.get(level, "")
    p = _LEVEL_PREFIX.get(level, "[    ]")
    print(f"{c}{Color.BOLD}{p}{Color.RESET}{c} {msg}{Color.RESET}", flush=True)


def banner(title: str) -> None:
    """Print a boxed section banner used to separate setup steps."""
    print(f"\n{Color.BOLD}{Color.BLUE}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{Color.RESET}\n")


def run(
    cmd: str,
    dry_run: bool = False,
    check: bool = False,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    """Run a shell command, echoing it first.

    In `dry_run` mode the command is only printed, not executed, and a
    fake successful CompletedProcess is returned so callers can chain
    logic without special-casing dry-run everywhere.
    """
    print(f"  $ {cmd}", flush=True)
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    try:
        result = subprocess.run(cmd, shell=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f"Command timed out after {timeout}s: {cmd}", "warn")
        return subprocess.CompletedProcess(cmd, 1, "", "timeout")
    if check and result.returncode != 0:
        log(f"Command failed (exit {result.returncode}): {cmd}", "error")
    return result


def run_capture(cmd: str, dry_run: bool = False) -> str:
    """Run a command and return its captured stdout (empty in dry-run)."""
    if dry_run:
        return ""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def pip_install(pip_bin: str, packages: Sequence[str], dry_run: bool, chunk_size: int = 20) -> None:
    """Install packages idempotently in chunks (pip skips already-satisfied specs)."""
    packages = list(packages)
    for i in range(0, len(packages), chunk_size):
        chunk = " ".join(f'"{p}"' for p in packages[i:i + chunk_size])
        run(f"{pip_bin} install --quiet {chunk}", dry_run=dry_run)


def get_conda_pip(conda_env: str) -> str:
    """Resolve the `pip` executable inside a named conda environment.

    Falls back to the bare `pip` command (relying on PATH / an already
    active environment) if the conda env cannot be resolved -- this
    keeps callers working during --dry-run or when conda is absent.
    """
    r = subprocess.run(
        f"conda run -n {conda_env} which pip",
        shell=True, capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else "pip"


def conda_available() -> bool:
    """Return True if the `conda` executable is on PATH."""
    return shutil.which("conda") is not None


def ensure_conda_env(
    conda_env: str,
    python_version: str,
    dry_run: bool,
    banner_title: str = "Conda Environment",
) -> None:
    """Create a conda environment if it doesn't already exist.

    Shared by every benchmark's setup.py; exits with an actionable
    error if `conda` itself is missing (common setup, i.e.
    `scripts/setup.py`, must be run first).
    """
    banner(banner_title)
    if not conda_available():
        log("conda not found -- run scripts/setup.py first", "error")
        sys.exit(1)
    result = subprocess.run("conda env list", shell=True, capture_output=True, text=True)
    if not dry_run and conda_env in (result.stdout or ""):
        log(f"Conda env '{conda_env}' already exists.", "ok")
    else:
        run(f"conda create -y -n {conda_env} python={python_version}", dry_run=dry_run)
        log(f"Conda env '{conda_env}' created (Python {python_version})", "ok")


def require_python_version(min_version: tuple, benchmark_name: str = "") -> None:
    """Exit with an actionable message if the running interpreter is too old.

    Should be called at the very top of a benchmark's setup.py, before
    any other imports that might require the newer syntax/features.
    """
    if sys.version_info < min_version:
        req = ".".join(str(v) for v in min_version)
        who = f" for {benchmark_name}" if benchmark_name else ""
        sys.exit(f"[ERROR] Python {req}+ required{who}. Current: {sys.version.split()[0]}")


def detect_os_family() -> str:
    """Detect the Linux distro family: 'centos' (RHEL-like) or 'ubuntu' (Debian-like)."""
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
    return "centos" if (shutil.which("dnf") or shutil.which("yum")) else "ubuntu"


def write_setup_marker(marker_path: Path, benchmark_label: str, extra_lines: Optional[List[str]] = None) -> None:
    """Write the `.setup_complete` marker file consumed by run.py's setup check.

    `extra_lines` can carry additional context (e.g. `conda_env: agentic`)
    that is purely informational for humans inspecting the marker file.
    """
    lines = [f"{benchmark_label} setup completed successfully"]
    if extra_lines:
        lines.extend(extra_lines)
    marker_path.write_text("\n".join(lines) + "\n")
    log(f"Setup marker written: {marker_path}", "ok")


__all__ = [
    "Color",
    "log",
    "banner",
    "run",
    "run_capture",
    "pip_install",
    "get_conda_pip",
    "conda_available",
    "ensure_conda_env",
    "require_python_version",
    "detect_os_family",
    "write_setup_marker",
]
