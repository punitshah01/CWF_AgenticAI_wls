#!/usr/bin/env bash
# misc/collect_rapl.sh — Snapshot RAPL power from powercap sysfs
# Usage:   bash misc/collect_rapl.sh [duration_s]  (default: 10 s)
# Output:  CSV: domain,avg_watts on stdout;  or save with -o <file>

DURATION="${1:-10}"
OUT_FILE=""
if [[ "$1" == "-o" ]]; then
    OUT_FILE="$2"
    DURATION="${3:-10}"
fi

RAPL_BASE="/sys/class/powercap/intel-rapl"

if [[ ! -d "${RAPL_BASE}" ]]; then
    echo "Error: RAPL sysfs not found at ${RAPL_BASE}" >&2
    exit 1
fi

# ── Discover domains ──────────────────────────────────────────────────────────
declare -A DOMAINS
for pkg in "${RAPL_BASE}"/intel-rapl:*; do
    [[ -f "${pkg}/energy_uj" ]] || continue
    name=$(cat "${pkg}/name" 2>/dev/null || echo "pkg")
    idx=$(basename "${pkg}" | cut -d: -f2)
    DOMAINS["${name}_${idx}"]="${pkg}/energy_uj"
    # Sub-domains (dram, uncore, …)
    for sub in "${pkg}"/intel-rapl:*/; do
        [[ -f "${sub}energy_uj" ]] || continue
        sub_name=$(cat "${sub}name" 2>/dev/null || echo "sub")
        sub_idx=$(basename "${sub}" | tr ':/' '_')
        DOMAINS["${sub_name}_${sub_idx}"]="${sub}energy_uj"
    done
done

if [[ ${#DOMAINS[@]} -eq 0 ]]; then
    echo "Error: no RAPL energy counters found" >&2
    exit 1
fi

# ── Baseline snapshot ─────────────────────────────────────────────────────────
declare -A E0
for domain in "${!DOMAINS[@]}"; do
    E0[$domain]=$(cat "${DOMAINS[$domain]}" 2>/dev/null || echo 0)
done

sleep "${DURATION}"

# ── Delta + compute watts ─────────────────────────────────────────────────────
header="domain,avg_watts"
echo "$header"
[[ -n "$OUT_FILE" ]] && echo "$header" > "$OUT_FILE"

for domain in $(echo "${!DOMAINS[@]}" | tr ' ' '\n' | sort); do
    e1=$(cat "${DOMAINS[$domain]}" 2>/dev/null || echo 0)
    e0=${E0[$domain]}
    delta=$(( e1 - e0 ))
    # Handle counter wrap
    if (( delta < 0 )); then
        max_uj_file=$(dirname "${DOMAINS[$domain]}")/max_energy_range_uj
        [[ -f "$max_uj_file" ]] && delta=$(( delta + $(cat "$max_uj_file") ))
    fi
    # μJ / s → W
    watts=$(awk "BEGIN {printf \"%.2f\", ${delta} / ${DURATION} / 1000000}")
    line="${domain},${watts}"
    echo "$line"
    [[ -n "$OUT_FILE" ]] && echo "$line" >> "$OUT_FILE"
done

[[ -n "$OUT_FILE" ]] && echo "[collect_rapl] Saved to ${OUT_FILE}" >&2
