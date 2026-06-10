#!/bin/bash
set -euo pipefail
# benchmarks/osworld/build/build.sh — Install OSWorld Python dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install -r "${SCRIPT_DIR}/requirements.txt"
python -m playwright install chromium 2>/dev/null || true
echo "[OK] OSWorld dependencies installed"
