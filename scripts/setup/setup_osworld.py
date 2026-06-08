#!/usr/bin/env python3
"""
scripts/setup/setup_osworld.py — Install OSWorld dependencies.

What this does:
  1. Verifies KVM / VT-x is enabled (/proc/cpuinfo vmx flag)
  2. Checks nested virtualization state
  3. Installs KVM + QEMU + libvirt packages
  4. Installs Docker CE
  5. Installs OSWorld system libs (OpenCV, audio, X11 headless, Playwright)
  6. Creates / reuses conda env 'agentic' with Python 3.10+
  7. Installs all OSWorld Python packages
  8. Clones github.com/xlang-ai/OSWorld and runs quickstart validation

Usage:
  python3 scripts/setup/setup_osworld.py [--dry-run] [--skip-kvm]
  # All extra flags are forwarded to scripts/setup.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETUP_PY = REPO_ROOT / "scripts" / "setup.py"


def _check_kvm() -> bool:
    """Return True if KVM hardware flags are present."""
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        return "vmx" in cpuinfo or "svm" in cpuinfo
    except OSError:
        return False


def _check_nested_virt() -> bool:
    """Return True if Intel nested virtualisation is enabled."""
    nested = Path("/sys/module/kvm_intel/parameters/nested")
    if nested.exists():
        return nested.read_text().strip() in ("1", "Y", "y")
    return False


def main() -> None:
    if "--skip-kvm" not in sys.argv and not _check_kvm():
        print("[WARN] KVM hardware flags (vmx/svm) NOT found in /proc/cpuinfo.")
        print("[WARN] OSWorld REQUIRES KVM. Enable VT-x / AMD-V in BIOS.")
        print("[WARN] Continuing anyway — setup will still install packages.")
    elif "--skip-kvm" not in sys.argv:
        print("[OK]  KVM flags found in /proc/cpuinfo")
        nested = _check_nested_virt()
        status = "enabled" if nested else "NOT enabled (may be needed for nested VMs)"
        print(f"[INFO] Nested virtualisation: {status}")
        if not nested:
            print("[INFO] To enable: sudo modprobe kvm_intel nested=1")

    extra = sys.argv[1:]
    cmd = [sys.executable, str(SETUP_PY), "--benchmarks", "osworld", *extra]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
