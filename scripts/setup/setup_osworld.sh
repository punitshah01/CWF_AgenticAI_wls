#!/usr/bin/env bash
# =============================================================================
# setup_osworld.sh — CWF Agentic AI: OSWorld Setup
# Ref: github.com/xlang-ai/OSWorld  |  xlang-ai, NeurIPS 2024
# Requirements: KVM/QEMU, Docker, 64 GB RAM, 100 GB storage
# Tasks: 369 (Linux + Windows GUIs across LibreOffice/Chrome/VSCode/GIMP/VLC)
# =============================================================================
set -euo pipefail

LOG_FILE="/tmp/cwf_setup_osworld.log"
exec > >(tee -a "$LOG_FILE") 2>&1

INSTALL_DIR="${CWF_WORKDIR:-$HOME/cwf_agentic}/osworld"
CONDA_ENV="${CONDA_ENV:-agentic}"

echo "============================================="
echo "CWF Agentic AI — OSWorld Setup"
echo "Install dir : $INSTALL_DIR"
echo "============================================="

# ── KVM check (hard requirement) ─────────────────────────────────────────────
echo "--- Checking KVM support ---"
KVM_COUNT=$(egrep -c '(vmx|svm)' /proc/cpuinfo || true)
if [ "$KVM_COUNT" -eq 0 ]; then
    echo "[ERROR] KVM not supported. OSWorld requires hardware virtualization."
    echo "        Check BIOS: VT-x (Intel) must be enabled."
    exit 1
fi
echo "[OK] KVM supported ($KVM_COUNT virt-capable CPUs)"

# Nested virt check
NESTED=$(cat /sys/module/kvm_intel/parameters/nested 2>/dev/null || echo "N")
if [ "$NESTED" == "Y" ] || [ "$NESTED" == "1" ]; then
    echo "[OK] Nested virtualization enabled"
else
    echo "[WARN] Nested virtualization not enabled. Enable with:"
    echo "       echo 'options kvm-intel nested=1' | sudo tee /etc/modprobe.d/kvm.conf"
    echo "       sudo modprobe -r kvm_intel && sudo modprobe kvm_intel nested=1"
fi

# Docker
docker info &>/dev/null || { echo "[ERROR] Docker not running"; exit 1; }
echo "[OK] Docker available"

# Memory
TOTAL_MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
[ "$TOTAL_MEM_GB" -lt 64 ] && echo "[WARN] < 64 GB RAM — fewer parallel VMs possible" || echo "[OK] Memory >= 64 GB"

FREE_DISK_GB=$(df -BG "$HOME" | awk 'NR==2 {gsub("G",""); print $4}')
[ "$FREE_DISK_GB" -lt 100 ] && echo "[WARN] < 100 GB free disk" || echo "[OK] Disk >= 100 GB"

# ── Clone ─────────────────────────────────────────────────────────────────────
mkdir -p "$(dirname "$INSTALL_DIR")"
if [ -d "$INSTALL_DIR" ]; then
    echo "[INFO] Pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only
else
    git clone https://github.com/xlang-ai/OSWorld.git "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# ── Install ───────────────────────────────────────────────────────────────────
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"
pip install -r requirements.txt --quiet
echo "[OK] OSWorld dependencies installed"

# ── Quickstart validation ─────────────────────────────────────────────────────
echo ""
echo "--- Quickstart validation ---"
echo "[INFO] Running quickstart.py (Docker provider) — pulls Ubuntu VM image"
python quickstart.py --provider_name docker \
    && echo "[OK] Quickstart passed" \
    || echo "[WARN] Quickstart failed — check KVM + Docker setup"

# ── Production run template ───────────────────────────────────────────────────
echo ""
echo "--- Production run (parallel, headless) ---"
cat << 'EOF'
# CWF recommended: 10 parallel envs, screenshot observation
# Each VM gets ~6-8 GB RAM, allocate env cores via cgroup
python scripts/python/run_multienv.py \
    --provider_name docker \
    --headless \
    --observation_type screenshot \
    --model local_llm \
    --sleep_after_execution 3 \
    --max_steps 15 \
    --num_envs 10 \
    --client_password password

# Show results by domain
python show_result.py --detailed
EOF

echo ""
echo "--- Scaling num_envs on CWF ---"
echo "  1 env  :  ~8 GB RAM  |  4–8 cores"
echo "  4 envs : ~32 GB RAM  | 16–32 cores"
echo "  8 envs : ~64 GB RAM  | 32–64 cores"
echo "  10 envs: ~80 GB RAM  | 40–80 cores (recommended max)"

echo ""
echo "============================================="
echo "[DONE] OSWorld setup complete. Log: $LOG_FILE"
echo "See: benchmarks/osworld/README.md"
echo "============================================="
