#!/usr/bin/env python3
"""
scripts/setup/setup_webarena.py — Install WebArena dependencies.

What this does:
  1. Installs Docker CE (needed for 6 self-hosted web service containers)
  2. Installs Playwright system libs
  3. Creates / reuses conda env 'agentic' with Python 3.10+
  4. Installs all WebArena Python packages
  5. Installs Playwright Chromium browser
  6. Writes ~/.cwf_webarena_env with service endpoint variables

Usage:
  python3 scripts/setup/setup_webarena.py [--dry-run]
  # All extra flags are forwarded to scripts/setup.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETUP_PY = REPO_ROOT / "scripts" / "setup.py"


def main() -> None:
    extra = sys.argv[1:]
    cmd = [sys.executable, str(SETUP_PY), "--benchmarks", "webarena", *extra]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))

    if result.returncode == 0:
        _write_webarena_env()

    sys.exit(result.returncode)


def _write_webarena_env() -> None:
    """Write ~/.cwf_webarena_env with service endpoint variables."""
    env_file = Path.home() / ".cwf_webarena_env"
    content = """\
# WebArena service endpoints — source this file before running evaluation
# Adjust HOSTURL if services run on a different host

export HOSTURL="${HOSTURL:-localhost}"

export SHOPPING="http://${HOSTURL}:7770"
export SHOPPING_ADMIN="http://${HOSTURL}:7780/admin"
export REDDIT="http://${HOSTURL}:9999"
export GITLAB="http://${HOSTURL}:8023"
export WIKIPEDIA="http://${HOSTURL}:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
export MAP="http://${HOSTURL}:3000"
export HOMEPAGE="http://${HOSTURL}:4399"

# Usage:
#   source ~/.cwf_webarena_env
#   cd ~/cwf_agentic/webarena
#   python scripts/generate_test_data.py
"""
    env_file.write_text(content)
    print(f"[setup_webarena] Wrote service endpoints to {env_file}")
    print(f"[setup_webarena] Run: source {env_file}")


if __name__ == "__main__":
    main()
