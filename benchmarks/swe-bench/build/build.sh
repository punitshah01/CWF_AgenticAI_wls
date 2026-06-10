#!/bin/bash
set -euo pipefail
# benchmarks/swe-bench/build/build.sh — Install SWE-bench Python dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install -r "${SCRIPT_DIR}/requirements.txt"
echo "[OK] SWE-bench dependencies installed"
