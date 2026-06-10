#!/bin/bash
set -euo pipefail
# setup/setup_platform.sh — Apply system tuning for consistent benchmark results on CWF.
#
# Run as root (or with sudo) before any benchmark run.
# Restores are NOT automatic — reboot to reset, or manually revert.
#
# Usage:
#   sudo bash setup/setup_platform.sh
#   sudo bash setup/setup_platform.sh --no-turbo   # also disable turbo boost

DISABLE_TURBO=0
for arg in "$@"; do
    [[ "${arg}" == "--no-turbo" ]] && DISABLE_TURBO=1
done

echo "=== CWF Platform Tuning ==="

# 1. CPU governor → performance
echo "[1/4] Setting CPU governor to 'performance' ..."
for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "${gov}" 2>/dev/null || true
done
# Verify
sample=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "n/a")
echo "      Governor cpu0: ${sample}"

# 2. Disable turbo boost (optional)
TURBO_PATH="/sys/devices/system/cpu/intel_pstate/no_turbo"
if [[ "${DISABLE_TURBO}" -eq 1 ]]; then
    echo "[2/4] Disabling Intel turbo boost ..."
    if [[ -f "${TURBO_PATH}" ]]; then
        echo 1 > "${TURBO_PATH}"
        echo "      no_turbo: $(cat ${TURBO_PATH})"
    else
        echo "      WARNING: ${TURBO_PATH} not found — turbo state unchanged"
    fi
else
    echo "[2/4] Turbo boost: unchanged (pass --no-turbo to disable)"
fi

# 3. Disable ASLR
echo "[3/4] Disabling ASLR (randomize_va_space → 0) ..."
echo 0 > /proc/sys/kernel/randomize_va_space
echo "      randomize_va_space: $(cat /proc/sys/kernel/randomize_va_space)"

# 4. Disable transparent huge pages defragmentation
echo "[4/4] Setting THP to madvise ..."
THP_PATH="/sys/kernel/mm/transparent_hugepage"
if [[ -d "${THP_PATH}" ]]; then
    echo madvise > "${THP_PATH}/enabled"  2>/dev/null || true
    echo defer+madvise > "${THP_PATH}/defrag" 2>/dev/null || true
    echo "      THP enabled: $(cat ${THP_PATH}/enabled)"
else
    echo "      WARNING: THP sysfs not found — skipping"
fi

echo ""
echo "[OK] Platform tuning complete. Reboot to restore defaults."
