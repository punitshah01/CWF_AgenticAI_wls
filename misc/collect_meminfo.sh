#!/usr/bin/env bash
# misc/collect_meminfo.sh — Snapshot /proc/meminfo into results/platform/
# Usage: bash misc/collect_meminfo.sh [output_dir]

OUT_DIR="${1:-results/platform}"
mkdir -p "${OUT_DIR}"
TS=$(date +%Y%m%d_%H%M%S)
OUT="${OUT_DIR}/meminfo_${TS}.txt"
cp /proc/meminfo "${OUT}"
echo "[collect_meminfo] Saved to ${OUT}"
