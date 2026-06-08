#!/usr/bin/env bash
# =============================================================================
# setup_swebench.sh — CWF Agentic AI: SWE-bench Setup
# Ref: github.com/SWE-bench/SWE-bench  |  ICLR 2024 Oral
# Requirements: Docker 24+, 120 GB storage, 16 GB RAM minimum
# =============================================================================
set -euo pipefail

LOG_FILE="/tmp/cwf_setup_swebench.log"
exec > >(tee -a "$LOG_FILE") 2>&1

INSTALL_DIR="${CWF_WORKDIR:-$HOME/cwf_agentic}/swebench"
CONDA_ENV="${CONDA_ENV:-agentic}"

echo "============================================="
echo "CWF Agentic AI — SWE-bench Setup"
echo "Install dir : $INSTALL_DIR"
echo "Conda env   : $CONDA_ENV"
echo "============================================="

# ── Pre-flight checks ─────────────────────────────────────────────────────────
echo "--- Pre-flight checks ---"

# Docker
if ! docker info &>/dev/null; then
    echo "[ERROR] Docker not running. Run: sudo systemctl start docker"
    exit 1
fi
echo "[OK] Docker available"

# Storage
FREE_DISK_GB=$(df -BG "$HOME" | awk 'NR==2 {gsub("G",""); print $4}')
[ "$FREE_DISK_GB" -lt 120 ] && echo "[WARN] < 120 GB free disk — Docker image pull may fail" || echo "[OK] Disk >= 120 GB"

# Memory
TOTAL_MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
[ "$TOTAL_MEM_GB" -lt 16 ] && echo "[WARN] < 16 GB RAM" || echo "[OK] Memory >= 16 GB"

# ── Clone ─────────────────────────────────────────────────────────────────────
echo ""
echo "--- Cloning SWE-bench ---"
mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -d "$INSTALL_DIR" ]; then
    echo "[INFO] $INSTALL_DIR already exists — pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only
else
    git clone https://github.com/SWE-bench/SWE-bench.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Install in conda env ──────────────────────────────────────────────────────
echo ""
echo "--- Installing Python dependencies ---"
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

pip install -e ".[test]" --quiet
echo "[OK] SWE-bench installed"

# ── Validate: gold-patch single task ─────────────────────────────────────────
echo ""
echo "--- Validation: gold patch on 1 task ---"
echo "[INFO] This will pull a Docker image (~2 min first run)"
python -m swebench.harness.run_evaluation \
    --predictions_path gold \
    --max_workers 1 \
    --instance_ids sympy__sympy-20590 \
    --run_id cwf_validate_gold \
    && echo "[OK] Validation passed" \
    || echo "[WARN] Validation failed — check Docker permissions / disk space"

# ── Useful benchmark sizes ────────────────────────────────────────────────────
echo ""
echo "--- SWE-bench Datasets ---"
echo "  SWE-bench Verified : 500 tasks (use for characterization)"
echo "  SWE-bench Lite     : 300 tasks (use for quick iteration)"
echo "  SWE-bench Full     : 2294 tasks"
echo ""
echo "--- Run example (Lite, 8 parallel workers) ---"
cat << 'EOF'
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --predictions_path <path_to_agent_predictions.jsonl> \
    --max_workers 8 \
    --run_id cwf_baseline

# CWF note: max_workers <= min(0.75 * nproc, 24) to leave headroom for LLM
# Each worker spins up 1 Docker container (~4-8 GB RAM)
EOF

echo ""
echo "============================================="
echo "[DONE] SWE-bench setup complete. Log: $LOG_FILE"
echo "See: benchmarks/swe-bench/README.md"
echo "============================================="
