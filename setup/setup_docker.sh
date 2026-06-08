#!/usr/bin/env bash
# setup/setup_docker.sh — Install Docker CE and configure for non-root use
# Mirrors pnpwls/setup/setup_docker.sh
set -euo pipefail

LOG_FILE="/tmp/cwf_setup_docker.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "============================================="
echo "CWF Agentic AI — Docker CE Setup"
echo "============================================="

if command -v docker &>/dev/null; then
    echo "[OK] Docker already installed: $(docker --version)"
    exit 0
fi

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS_ID="$ID"
else
    OS_ID="unknown"
fi

if [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" ]]; then
    echo "[INFO] Installing Docker CE on Ubuntu/Debian …"
    sudo apt-get remove -y docker docker.io containerd runc 2>/dev/null || true
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
else
    echo "[INFO] Installing Docker CE on CentOS/RHEL …"
    sudo dnf remove -y docker docker-client docker-common 2>/dev/null || true
    sudo dnf install -y yum-utils
    sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "${USER}" || true
docker run --rm hello-world && echo "[OK] Docker operational"

echo ""
echo "============================================="
echo "[DONE] Docker setup complete. Log: ${LOG_FILE}"
echo "Note: re-login for group membership to take effect."
echo "============================================="
