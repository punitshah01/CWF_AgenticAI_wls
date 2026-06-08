#!/usr/bin/env bash
# =============================================================================
# misc/process_emon.sh — Post-process raw EMON file with EDP (pyedp / edp.rb)
#
# Usage:  bash misc/process_emon.sh <emon_file> [platform] [sockets]
# Output: emon/<session>/processed_metrics.* + moved raw emon file
#
# Platforms: clearwaterforest | diamondrapids | graniterapids | sierraforest |
#            emeraldrapids | sapphirerapids | icelake | cascadelake
# =============================================================================

set -euo pipefail

abs_dir=$(dirname "$(realpath "$0")")

# ── Auto-detect platform if not supplied ──────────────────────────────────────
PLATFORM="${2:-$(bash "${abs_dir}/detect_platform.sh")}"
SOCKETS="${3:-$(lscpu | awk '/^Socket\(s\):/{print $NF}')}"
total_cores=$(lscpu | awk '/^CPU\(s\):/{print $NF; exit}')

sep_dir="/opt/intel/sep"
edp_dir="${sep_dir}/config/edp"
start_sample=50
dirty_end_samples=100

# ── EDP platform → subdirectory mapping ──────────────────────────────────────
declare -A EDP_SUBDIR=(
    [clearwaterforest]="ClearwaterForest"
    [diamondrapids]="DiamondRapids"
    [graniterapids]="GraniteRapids"
    [sierraforest]="SierraForest"
    [emeraldrapids]="EmeraldRapids"
    [sapphirerapids]="SapphireRapids"
    [icelake]="IceLake"
    [cascadelake]="CascadeLake"
    [cooperlake]="CooperLake"
    [skylake]="SkyLake"
)

# ── Parse arguments ───────────────────────────────────────────────────────────
print_usage() { echo -e "\nUsage: $0 <emon_file> [platform] [sockets]\n"; exit 1; }

emon_file="${1:-}"
[[ -z "$emon_file" ]] && { echo "Error: missing emon_file argument"; print_usage; }
[[ "$emon_file" == "-h" || "$emon_file" == "--help" ]] && print_usage
[[ ! -f "$emon_file" ]] && { echo "Error: file not found: $emon_file"; exit 1; }

# ── Output directory ──────────────────────────────────────────────────────────
session=$(basename "${emon_file%.*}")
output_dir="results/platform/emon/${session}"
mkdir -p "${output_dir}"

# ── Sample range ──────────────────────────────────────────────────────────────
total_samples=$(grep -c "INST_RETIRED.ANY" "${emon_file}" 2>/dev/null || echo 200)
stop_sample=$(( total_samples - dirty_end_samples ))
[[ $stop_sample -lt 1 ]] && stop_sample=1

echo "[process_emon] Platform: ${PLATFORM}  Sockets: ${SOCKETS}"
echo "[process_emon] EMON file: ${emon_file}  Samples: ${total_samples}"
echo "[process_emon] Range: begin=${start_sample}  end=${stop_sample}"

# ── Load SEP environment ──────────────────────────────────────────────────────
if [[ -f "${sep_dir}/sep_vars.sh" ]]; then
    # shellcheck source=/dev/null
    source "${sep_dir}/sep_vars.sh"
fi

# ── Try pyedp first (preferred), fall back to jruby edp.rb ───────────────────
pyedp="${edp_dir}/pyedp/pyedp.py"
edp_rb="${edp_dir}/edp.rb"

edp_subdir="${EDP_SUBDIR[$PLATFORM]:-$PLATFORM}"
xml_pattern="${edp_dir}/Architecture*/${edp_subdir}/*${SOCKETS}s*.xml"

if [[ -f "${pyedp}" ]]; then
    echo "[process_emon] Using pyedp …"
    python3 "${pyedp}" \
        -i "${emon_file}" \
        -b "${start_sample}" -e "${stop_sample}" \
        --socket-view \
        -o "${output_dir}/processed_metrics"
elif [[ -f "${edp_rb}" ]]; then
    echo "[process_emon] Using jruby edp.rb …"
    FreeMEM=$(free -m | awk 'NR==2{print $4}')
    FreeMEM=$(( FreeMEM - 1024 ))
    jruby_opts="-J-Xmx${FreeMEM}m -J-Xms${FreeMEM}m"
    # shellcheck disable=SC2086
    jruby ${jruby_opts} "${edp_rb}" \
        -i "${emon_file}" -m ${xml_pattern} \
        --socket-view \
        -o "${output_dir}/processed_metrics" \
        -b "${start_sample}" -e "${stop_sample}" \
        -p "$(( total_cores * 3 / 4 ))" -s 1
else
    echo "[process_emon] Neither pyedp nor edp.rb found — EDP skipped." >&2
    exit 1
fi

# Move generated CSVs and raw file into output directory
mv __mpp_* "${output_dir}/" 2>/dev/null || true
mv "${emon_file}"  "${output_dir}/" 2>/dev/null || true

echo "[process_emon] Done → ${output_dir}"
