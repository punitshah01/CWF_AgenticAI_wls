#!/bin/bash
set -euo pipefail
# benchmarks/t-bench/build/build.sh — Install T-Bench Python dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install -r "${SCRIPT_DIR}/requirements.txt"
echo "[OK] T-Bench dependencies installed"
