#!/bin/bash
set -euo pipefail
# benchmarks/osworld/run_osworld.sh — Shell entry point for OSWorld on CWF

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

output_dir="results/osworld"
args=("$@")
for i in "${!args[@]}"; do
    if [[ "${args[$i]}" == "--output-dir" && $((i+1)) -lt ${#args[@]} ]]; then
        output_dir="${args[$((i+1))]}"
    fi
done
mkdir -p "${output_dir}"

if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.venv/bin/activate"
elif [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
    :
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting OSWorld run" | tee "${output_dir}/run.log"
python "${SCRIPT_DIR}/run_osworld.py" "$@" 2>&1 | tee -a "${output_dir}/run.log"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] OSWorld run complete" | tee -a "${output_dir}/run.log"
