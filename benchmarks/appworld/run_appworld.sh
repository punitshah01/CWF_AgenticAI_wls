#!/bin/bash
set -euo pipefail
# benchmarks/appworld/run_appworld.sh — Shell entry point for AppWorld on CWF
#
# Usage:
#   ./benchmarks/appworld/run_appworld.sh
#   ./benchmarks/appworld/run_appworld.sh --output-dir results/appworld --iterations 3
#   ./benchmarks/appworld/run_appworld.sh --config benchmarks/appworld/config/default_config.yaml

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Parse --output-dir from args so we can tee logs there ─────────────────────
output_dir="results/appworld"
args=("$@")
for i in "${!args[@]}"; do
    if [[ "${args[$i]}" == "--output-dir" && $((i+1)) -lt ${#args[@]} ]]; then
        output_dir="${args[$((i+1))]}"
    fi
done
mkdir -p "${output_dir}"

# ── Activate venv if present ──────────────────────────────────────────────────
if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.venv/bin/activate"
elif [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
    : # already inside a conda env
fi

# ── Run benchmark, tee stdout+stderr to run.log ───────────────────────────────
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting AppWorld run" | tee "${output_dir}/run.log"
python "${SCRIPT_DIR}/run_appworld.py" "$@" 2>&1 | tee -a "${output_dir}/run.log"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] AppWorld run complete" | tee -a "${output_dir}/run.log"
