#!/bin/bash
set -euo pipefail
# benchmarks/webarena/build/build.sh — Install WebArena Python dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install -r "${SCRIPT_DIR}/requirements.txt"
python -m playwright install chromium
echo "[OK] WebArena dependencies installed"
