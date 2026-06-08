#!/usr/bin/env python3
"""
benchmarks/webarena/setup.py — Install WebArena dependencies on CWF.

What this does:
  1. Installs Docker CE (6 self-hosted service containers)
  2. Installs Playwright system libs + Chromium browser
  3. Creates / reuses conda env 'agentic' (Python 3.10+)
  4. Installs all WebArena Python packages
  5. Writes ~/.cwf_webarena_env with service endpoint variables

Usage:
  python3 benchmarks/webarena/setup.py
  python3 benchmarks/webarena/setup.py --dry-run
  python3 benchmarks/webarena/setup.py --registry localhost:5000
"""

import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit(f"[ERROR] Python 3.10+ required. Current: {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _write_env_file() -> None:
    env_file = Path.home() / ".cwf_webarena_env"
    env_file.write_text("""\
# WebArena service endpoints — source before running evaluation
# Adjust HOSTURL if services run on a different host
export HOSTURL="${HOSTURL:-localhost}"
export SHOPPING="http://${HOSTURL}:7770"
export SHOPPING_ADMIN="http://${HOSTURL}:7780/admin"
export REDDIT="http://${HOSTURL}:9999"
export GITLAB="http://${HOSTURL}:8023"
export WIKIPEDIA="http://${HOSTURL}:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
export MAP="http://${HOSTURL}:3000"
export HOMEPAGE="http://${HOSTURL}:4399"
""")
    print(f"[setup_webarena] Service endpoints written to {env_file}")
    print(f"[setup_webarena] Run: source {env_file}")


def main() -> None:
    extra = sys.argv[1:]
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "setup.py"),
        "--benchmarks", "webarena",
        *extra,
    ]
    rc = subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode
    if rc == 0:
        _write_env_file()
    sys.exit(rc)


if __name__ == "__main__":
    main()
