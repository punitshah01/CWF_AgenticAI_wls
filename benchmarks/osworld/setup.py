#!/usr/bin/env python3
"""
benchmarks/osworld/setup.py — Install OSWorld dependencies on CWF.

What this does:
  1. Verifies KVM / VT-x support (/proc/cpuinfo vmx flag)
  2. Installs KVM + QEMU + libvirt packages
  3. Installs Docker CE (VM controller runs in Docker)
  4. Installs OSWorld system libs (OpenCV, audio, X11 headless, Playwright)
  5. Creates / reuses conda env 'agentic' (Python 3.10+)
  6. Installs all OSWorld Python packages
  7. Clones github.com/xlang-ai/OSWorld and runs quickstart validation

Hard requirement: KVM / VT-x must be enabled in BIOS.

Usage:
  python3 benchmarks/osworld/setup.py
  python3 benchmarks/osworld/setup.py --dry-run
  python3 benchmarks/osworld/setup.py --skip-kvm      # skip KVM check/install
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _check_kvm() -> bool:
    try:
        return "vmx" in Path("/proc/cpuinfo").read_text()
    except OSError:
        return False


def main() -> None:
    extra = sys.argv[1:]

    if "--skip-kvm" not in extra and not _check_kvm():
        print("[WARN] KVM flags not found in /proc/cpuinfo.")
        print("[WARN] OSWorld REQUIRES KVM. Enable VT-x in BIOS before continuing.")
    elif "--skip-kvm" not in extra:
        print("[OK]  KVM flags present")

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "setup.py"),
        "--benchmarks", "osworld",
        *extra,
    ]
    sys.exit(subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode)


if __name__ == "__main__":
    main()
