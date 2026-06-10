#!/bin/bash
set -euo pipefail
# setup/setup_venv.sh — Create a Python virtual environment and install root requirements.
#
# Usage:
#   bash setup/setup_venv.sh
#   bash setup/setup_venv.sh --python python3.11   # explicit Python version
#   bash setup/setup_venv.sh --venv-dir /opt/cwf-venv

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="python3"
VENV_DIR="${REPO_ROOT}/.venv"

# Parse optional args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)   PYTHON_BIN="$2"; shift 2 ;;
        --venv-dir) VENV_DIR="$2";   shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

echo "=== CWF Python venv setup ==="
echo "Python  : ${PYTHON_BIN}"
echo "Venv dir: ${VENV_DIR}"
echo "Repo    : ${REPO_ROOT}"
echo ""

# Create venv if it doesn't already exist
if [[ -d "${VENV_DIR}" ]]; then
    echo "[INFO] Venv already exists at ${VENV_DIR} — skipping creation"
else
    echo "[INFO] Creating virtual environment ..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    echo "[ OK ] Venv created"
fi

# Activate
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
echo "[INFO] Activated: ${VIRTUAL_ENV}"

# Upgrade pip/setuptools/wheel first (idempotent)
echo "[INFO] Upgrading pip/setuptools/wheel ..."
pip install --quiet --upgrade pip setuptools wheel

# Install root requirements.txt if it exists
ROOT_REQS="${REPO_ROOT}/requirements.txt"
if [[ -f "${ROOT_REQS}" ]]; then
    echo "[INFO] Installing ${ROOT_REQS} ..."
    pip install --quiet -r "${ROOT_REQS}"
    echo "[ OK ] Root requirements installed"
else
    echo "[WARN] No root requirements.txt found — skipping"
fi

echo ""
echo "[ OK ] Venv ready. To activate:"
echo "       source ${VENV_DIR}/bin/activate"
