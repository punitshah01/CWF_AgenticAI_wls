#!/bin/bash
set -euo pipefail
# benchmarks/appworld/build/build.sh — Install AppWorld Python dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install -r "${SCRIPT_DIR}/requirements.txt"
echo "[OK] AppWorld dependencies installed"
