#!/usr/bin/env bash
# =============================================================================
# setup/setup_emon.sh — Install Intel SEP / EMON and configure pyedp
# Mirrors pnpwls/setup/setup_emon.sh, updated for CWF platform.
#
# Downloads SEP from Intel artifactory, installs drivers, sets up pyedp.
# =============================================================================
set -euo pipefail

abs_dir=$(dirname "$(realpath "$0")")

LOG_FILE="/tmp/cwf_setup_emon.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "============================================="
echo "CWF Agentic AI — SEP/EMON Setup"
echo "Date: $(date)"
echo "============================================="

# ── Platform check ────────────────────────────────────────────────────────────
PLATFORM=$(bash "${abs_dir}/../misc/detect_platform.sh")
echo "[INFO] Detected platform: ${PLATFORM}"

model=$(lscpu | awk '/^Model:/{print $NF}')
family=$(lscpu | grep -v BIOS | awk '/^CPU family:/{print $NF}')
echo "[INFO] CPU family=${family} model=${model}"

# ── SEP version (update this when a newer beta is available) ──────────────────
SEP_VERSION="sep_private_5_58_beta_linux_020402465cf386d3e"
ARTIFACTORY_BASE="https://ubit-artifactory-or.intel.com/artifactory/dpgpaivsoworkloads-or-local/utils/emon"

KEYDIR="${HOME}/devtools"
SEP_DIR="${KEYDIR}/${SEP_VERSION}"
INSTALL_DIR="/opt/intel/sep"

# ── Download ──────────────────────────────────────────────────────────────────
mkdir -p "${KEYDIR}"
cd "${KEYDIR}"

if [[ -d "${SEP_DIR}" ]]; then
    echo "[INFO] SEP archive already extracted at ${SEP_DIR} — skipping download"
else
    echo "[INFO] Downloading SEP ${SEP_VERSION} …"
    wget --no-proxy "${ARTIFACTORY_BASE}/${SEP_VERSION}.tar.bz2" \
         -O "${SEP_VERSION}.tar.bz2"
    tar xvf "${SEP_VERSION}.tar.bz2"
    rm -f "${SEP_VERSION}.tar.bz2"
    echo "[OK] Extracted to ${SEP_DIR}"
fi

# ── Install ───────────────────────────────────────────────────────────────────
cd "${SEP_DIR}"
echo "[INFO] Running sep-installer …"
./sep-installer.sh --accept-license -ni -u -i
echo "[OK] SEP installed to ${INSTALL_DIR}"

# ── pyedp ─────────────────────────────────────────────────────────────────────
PYEDP_DIR="${INSTALL_DIR}/config/edp/pyedp"
if [[ -d "${PYEDP_DIR}" ]]; then
    echo "[INFO] Installing pyedp Python dependencies …"
    python3 -m pip install -U numpy pandas defusedxml pytz xlsxwriter \
        multiprocess tables natsort tqdm dataclasses polars openpyxl \
        pyarrow jsonschema
    python3 -m pip install .
    echo "[OK] pyedp ready at ${PYEDP_DIR}"
else
    echo "[WARN] pyedp directory not found at ${PYEDP_DIR}"
fi

# ── Validate ──────────────────────────────────────────────────────────────────
source "${INSTALL_DIR}/sep_vars.sh"
EMON_VER=$(emon -v 2>&1 | awk '/SEP Driver Version/{print $(NF-1)}' || echo "unknown")
echo "[INFO] SEP version: ${EMON_VER}"

# ── TMC (Telemetry Manager Client) — optional ─────────────────────────────────
if [[ ! -d "${HOME}/tmc" ]]; then
    echo "[INFO] Installing TMC telemetry client …"
    git clone https://github.com/intel-sandbox/tools.dcso.telemetry.client.git "${HOME}/tmc" \
        && bash "${HOME}/tmc/install.sh"
fi

echo ""
echo "============================================="
echo "[DONE] SEP/EMON setup complete. Log: ${LOG_FILE}"
echo "Verify: source ${INSTALL_DIR}/sep_vars.sh && emon -v"
echo "Check:  bash misc/check_emon_setup.sh"
echo "============================================="
