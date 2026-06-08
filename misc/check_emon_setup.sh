#!/usr/bin/env bash
# =============================================================================
# misc/check_emon_setup.sh — Verify EMON/SEP installation before a run.
# Returns 1 if EMON is available, 0 if not (so callers can skip collection).
#
# Usage:  collect_emon=$(bash misc/check_emon_setup.sh)
#         if [[ $collect_emon -eq 1 ]]; then ...
# =============================================================================

abs_dir=$(dirname "$(realpath "$0")")
sep_dir="/opt/intel/sep"
edp_dir="${sep_dir}/config/edp"
timeout_secs=7
collect_emon=1

# ── Check SEP installation ────────────────────────────────────────────────────
if [[ ! -d ${sep_dir} ]]; then
    read -rst ${timeout_secs} \
        -p "
    Warning: EMON not found at ${sep_dir}.
             Run will continue WITHOUT EMON in ${timeout_secs}s.
             Press N to abort, any other key or wait to continue: " \
        -n 1 -r
    if [[ "$REPLY" =~ ^[nN]$ ]]; then
        echo -e "\nAborting.\n" >&2
        exit 1
    fi
    collect_emon=0
    echo ${collect_emon}
    exit 0
fi

# ── Load kernel drivers if not already loaded ─────────────────────────────────
SEP_DRIVER=$(lsmod | grep -c sepint || true)
if [[ ${SEP_DRIVER} -lt 1 ]]; then
    pushd "${sep_dir}/sepdk/src" > /dev/null || exit 1
    sudo ./rmmod-sep  2>/dev/null || true
    sudo ./build-driver -ni --no-udev
    sudo ./insmod-sep
    popd > /dev/null
fi

# ── Source sep_vars and check version ────────────────────────────────────────
# shellcheck source=/dev/null
source "${sep_dir}/sep_vars.sh"
sep_version=$(emon -v 2>&1 | awk '/SEP Driver Version/{print $(NF-1)}')

if [[ -z "$sep_version" ]]; then
    echo "Warning: Could not determine SEP version — continuing anyway." >&2
    echo ${collect_emon}
    exit 0
fi

# SEP >= 5.32 required
major=$(echo "$sep_version" | cut -d. -f1)
minor=$(echo "$sep_version" | cut -d. -f2)
if [[ $major -lt 5 ]] || { [[ $major -eq 5 ]] && [[ $minor -lt 32 ]]; }; then
    echo -e "\nError: SEP ${sep_version} too old. Need >= 5.32." >&2
    echo -e "Install newer SEP: bash setup/setup_emon.sh\n" >&2
    collect_emon=0
fi

echo ${collect_emon}
