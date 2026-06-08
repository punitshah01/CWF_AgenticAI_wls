#!/usr/bin/env bash
# =============================================================================
# setup_base.sh — CWF Agentic AI: Base System Prerequisites
# Target OS: Ubuntu 22.04+ / RHEL 9+
# Platform: Clearwater Forest (CWF), E-core Darkmont, no SMT
# =============================================================================
set -euo pipefail

LOG_FILE="/tmp/cwf_setup_base.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "============================================="
echo "CWF Agentic AI — Base System Setup"
echo "Date: $(date)"
echo "Host: $(hostname)"
echo "============================================="

# ── Detect OS ────────────────────────────────────────────────────────────────
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_VER="$VERSION_ID"
    echo "[INFO] OS: $PRETTY_NAME"
else
    echo "[ERROR] Cannot detect OS. Aborting."
    exit 1
fi

# ── Verify KVM support (required for OSWorld) ─────────────────────────────
echo ""
echo "--- Checking KVM support ---"
KVM_COUNT=$(egrep -c '(vmx|svm)' /proc/cpuinfo || true)
if [ "$KVM_COUNT" -gt 0 ]; then
    echo "[OK] KVM supported ($KVM_COUNT logical CPUs with virt extensions)"
else
    echo "[WARN] KVM flags not found. OSWorld will require nested virtualization."
fi

# ── System info ──────────────────────────────────────────────────────────────
TOTAL_CORES=$(nproc --all)
TOTAL_MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
FREE_DISK_GB=$(df -BG / | awk 'NR==2 {gsub("G",""); print $4}')
echo "[INFO] CPU cores : $TOTAL_CORES"
echo "[INFO] Memory    : ${TOTAL_MEM_GB} GB"
echo "[INFO] Free disk : ${FREE_DISK_GB} GB"

[ "$TOTAL_MEM_GB" -lt 128 ] && echo "[WARN] < 128 GB RAM — large models may fail" || echo "[OK] Memory >= 128 GB"
[ "$FREE_DISK_GB" -lt 500 ] && echo "[WARN] < 500 GB free disk — consider adding storage" || echo "[OK] Disk >= 500 GB"

# ── Package installation ──────────────────────────────────────────────────────
echo ""
echo "--- Installing system packages ---"

if [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" ]]; then
    sudo apt-get update -y
    sudo apt-get install -y \
        docker.io docker-buildx \
        qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils \
        python3.11 python3.11-venv python3.11-dev python3-pip \
        git git-lfs curl wget htop numactl hwloc \
        build-essential cmake pkg-config \
        linux-tools-common linux-tools-generic \
        msr-tools cpufrequtils
elif [[ "$OS_ID" == "rhel" || "$OS_ID" == "centos" || "$OS_ID" == "fedora" ]]; then
    sudo dnf install -y \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
        qemu-kvm libvirt python3.11 git git-lfs \
        curl wget htop numactl hwloc \
        gcc gcc-c++ cmake \
        msr-tools cpufrequtils || \
    sudo dnf install -y \
        podman qemu-kvm libvirt python3.11 git git-lfs \
        numactl hwloc gcc gcc-c++ cmake msr-tools
fi

# ── Docker ────────────────────────────────────────────────────────────────────
echo ""
echo "--- Configuring Docker ---"
sudo systemctl enable --now docker || true
sudo usermod -aG docker "$USER" || true
docker run --rm hello-world && echo "[OK] Docker working" || echo "[WARN] Docker test failed — may need re-login for group membership"

# ── libvirtd ─────────────────────────────────────────────────────────────────
echo ""
echo "--- Configuring libvirt/KVM ---"
sudo systemctl enable --now libvirtd || true

# ── Conda / Miniconda ─────────────────────────────────────────────────────────
echo ""
echo "--- Conda setup ---"
if ! command -v conda &>/dev/null; then
    echo "[INFO] Installing Miniconda..."
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    wget -q "$MINICONDA_URL" -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p "$HOME/miniconda3"
    eval "$("$HOME/miniconda3/bin/conda" shell.bash hook)"
    conda init bash
    echo "[OK] Miniconda installed at $HOME/miniconda3"
else
    echo "[OK] conda already available: $(conda --version)"
fi

# ── Create agentic conda environment ─────────────────────────────────────────
CONDA_ENV="agentic"
if conda env list | grep -q "^$CONDA_ENV "; then
    echo "[INFO] Conda env '$CONDA_ENV' already exists — skipping create"
else
    conda create -y -n "$CONDA_ENV" python=3.11
    echo "[OK] Conda env '$CONDA_ENV' created"
fi

echo ""
echo "--- Activate with: conda activate $CONDA_ENV ---"

# ── git-lfs ──────────────────────────────────────────────────────────────────
git lfs install --system || git lfs install || true

# ── numactl topology dump ─────────────────────────────────────────────────────
echo ""
echo "--- Platform topology ---"
numactl -H || lscpu | grep -E "NUMA|Socket|Core|Thread|CPU\(s\)"

echo ""
echo "============================================="
echo "[DONE] Base setup complete. Log: $LOG_FILE"
echo "Next: bash scripts/setup/setup_appworld.sh"
echo "============================================="
