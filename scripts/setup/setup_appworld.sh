#!/usr/bin/env bash
# =============================================================================
# setup_appworld.sh — CWF Agentic AI: AppWorld Setup
# Ref: github.com/StonyBrookNLP/appworld  |  ACL 2024 Best Resource
# Requirements: Python 3.11+, 8 GB RAM, 10 GB storage
# Apps: Amazon, Spotify, Gmail, Calendar, Venmo, Phone, Supervisor, Notes, File
# =============================================================================
set -euo pipefail

LOG_FILE="/tmp/cwf_setup_appworld.log"
exec > >(tee -a "$LOG_FILE") 2>&1

CONDA_ENV="${CONDA_ENV:-agentic}"
APPWORLD_WORK_DIR="${CWF_WORKDIR:-$HOME/cwf_agentic}/appworld"

echo "============================================="
echo "CWF Agentic AI — AppWorld Setup"
echo "Work dir  : $APPWORLD_WORK_DIR"
echo "Conda env : $CONDA_ENV"
echo "============================================="

# ── Pre-flight ────────────────────────────────────────────────────────────────
PYTHON_VER=$(python3 --version 2>&1 | awk '{print $2}')
echo "[INFO] Python version: $PYTHON_VER"

TOTAL_MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
[ "$TOTAL_MEM_GB" -lt 8 ] && echo "[WARN] < 8 GB RAM" || echo "[OK] Memory >= 8 GB"

# ── Activate conda env ────────────────────────────────────────────────────────
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

# ── pip install appworld ──────────────────────────────────────────────────────
echo ""
echo "--- Installing appworld package ---"
pip install appworld --quiet
echo "[OK] appworld installed: $(pip show appworld | grep Version)"

# ── appworld install (downloads data bundles) ─────────────────────────────────
echo ""
echo "--- Running appworld install (~2-3 min, downloads bundles via git-lfs) ---"
mkdir -p "$APPWORLD_WORK_DIR"
cd "$APPWORLD_WORK_DIR"
appworld install
echo "[OK] appworld install complete"

# ── Download datasets ─────────────────────────────────────────────────────────
echo ""
echo "--- Downloading task datasets ---"
appworld download data
echo "[OK] Data downloaded"

# ── Verification ──────────────────────────────────────────────────────────────
echo ""
echo "--- Verifying installation ---"
appworld verify tests  && echo "[OK] Tests verified"
appworld verify tasks  && echo "[OK] Tasks verified"

# ── Clone experiments package (for agent runners) ─────────────────────────────
echo ""
echo "--- Installing agent experiments ---"
if [ ! -d "$APPWORLD_WORK_DIR/appworld_repo" ]; then
    git clone https://github.com/StonyBrookNLP/appworld.git "$APPWORLD_WORK_DIR/appworld_repo"
fi
cd "$APPWORLD_WORK_DIR/appworld_repo"
pip install -e "experiments[simplified]" --quiet || \
    pip install -e ".[simplified]" --quiet || \
    echo "[WARN] experiments[simplified] install failed — run manually"

# ── Environment variables for local LLM ──────────────────────────────────────
echo ""
echo "--- LLM endpoint configuration ---"
cat << 'EOF'
# Set these before running agent (vLLM must be running on :8000):
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="not-needed"
EOF

# ── Run commands ──────────────────────────────────────────────────────────────
echo ""
echo "--- Run commands ---"
cat << 'EOF'
# Datasets: train | dev | test_normal | test_challenge
# Agent types: simplified_function_calling_agent | react_agent

# Quick dev validation (fast feedback)
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="not-needed"
appworld run auto \
    --agent-name simplified_function_calling_agent \
    --model-name local-llm \
    --dataset-name dev

# Full test_normal run
appworld run auto \
    --agent-name simplified_function_calling_agent \
    --model-name local-llm \
    --dataset-name test_normal

# Evaluate
appworld evaluate cwf_baseline test_normal

# Multi-instance: run N copies simultaneously (each on its own port)
# The AppWorld server is lightweight — scale to 4-8 parallel instances
EOF

echo ""
echo "============================================="
echo "[DONE] AppWorld setup complete. Log: $LOG_FILE"
echo "See: benchmarks/appworld/README.md"
echo "============================================="
