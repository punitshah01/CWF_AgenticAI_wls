#!/usr/bin/env bash
# =============================================================================
# setup_webarena.sh — CWF Agentic AI: WebArena Setup
# Ref: github.com/web-arena-x/webarena  |  CMU, NeurIPS 2023
# Requirements: Docker, 50 GB storage, 32 GB RAM, 812 tasks
# Services: Shopping (7770), CMS Admin (7780), Reddit (9999),
#            GitLab (8023), Wikipedia (8888), Map (3000)
# =============================================================================
set -euo pipefail

LOG_FILE="/tmp/cwf_setup_webarena.log"
exec > >(tee -a "$LOG_FILE") 2>&1

INSTALL_DIR="${CWF_WORKDIR:-$HOME/cwf_agentic}/webarena"
CONDA_ENV="${CONDA_ENV:-webarena}"

echo "============================================="
echo "CWF Agentic AI — WebArena Setup"
echo "Install dir : $INSTALL_DIR"
echo "============================================="

# ── Pre-flight ────────────────────────────────────────────────────────────────
docker info &>/dev/null || { echo "[ERROR] Docker not running"; exit 1; }
echo "[OK] Docker available"

FREE_DISK_GB=$(df -BG "$HOME" | awk 'NR==2 {gsub("G",""); print $4}')
[ "$FREE_DISK_GB" -lt 50 ] && echo "[WARN] < 50 GB free disk" || echo "[OK] Disk >= 50 GB"

# ── Clone ─────────────────────────────────────────────────────────────────────
mkdir -p "$(dirname "$INSTALL_DIR")"
if [ -d "$INSTALL_DIR" ]; then
    echo "[INFO] Pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only
else
    git clone https://github.com/web-arena-x/webarena.git "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# ── Python env ────────────────────────────────────────────────────────────────
eval "$(conda shell.bash hook)"
conda create -y -n "$CONDA_ENV" python=3.10 || true
conda activate "$CONDA_ENV"
pip install -r requirements.txt --quiet
playwright install chromium
pip install -e . --quiet
echo "[OK] Python dependencies installed"

# ── Deploy web services ───────────────────────────────────────────────────────
echo ""
echo "--- Deploying 5 WebArena web services via Docker ---"
echo "[INFO] See environment_docker/README.md for full details"
echo "[INFO] Services require ~20 GB Docker images on first pull"
echo ""
echo "Port assignments:"
echo "  Shopping       : 7770"
echo "  Shopping Admin : 7780"
echo "  Reddit         : 9999"
echo "  GitLab         : 8023"
echo "  Wikipedia      : 8888"
echo "  Map (OSRM)     : 3000"
echo ""

# ── Export environment variables ──────────────────────────────────────────────
WEBARENA_ENV_FILE="$HOME/.cwf_webarena_env"
cat > "$WEBARENA_ENV_FILE" << 'EOF'
export SHOPPING="localhost:7770"
export SHOPPING_ADMIN="localhost:7780/admin"
export REDDIT="localhost:9999"
export GITLAB="localhost:8023"
export MAP="localhost:3000"
export WIKIPEDIA="localhost:8888/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing"
EOF
echo "[OK] Environment variables written to $WEBARENA_ENV_FILE"
echo "     Source with: source $WEBARENA_ENV_FILE"

# ── Post-service setup ────────────────────────────────────────────────────────
echo ""
echo "--- After starting Docker services, run: ---"
cat << 'EOF'
source ~/.cwf_webarena_env

# Generate test configs
python scripts/generate_test_data.py

# Get auto-login cookies
mkdir -p ./.auth
python browser_env/auto_login.py

# Run evaluation (all 812 tasks)
python run.py \
    --instruction_path agent/prompts/jsons/p_cot_id_actree_2s.json \
    --test_start_idx 0 \
    --test_end_idx 812 \
    --model local_llm \
    --result_dir ./results_cwf

# CWF note: Pin Playwright workers to env-only cpuset to avoid
# contention with LLM inference cores:
#   taskset -c 100-143 python run.py ...
EOF

echo ""
echo "============================================="
echo "[DONE] WebArena setup complete. Log: $LOG_FILE"
echo "See: benchmarks/webarena/README.md"
echo "============================================="
