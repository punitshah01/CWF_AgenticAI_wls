#!/usr/bin/env bash
# =============================================================================
# misc/detect_platform.sh — Detect Intel CPU platform codename
# Mirrors pnpwls/misc/detect_platform.sh, extended for CWF as primary target.
#
# Output: one of:
#   clearwaterforest | diamondrapids | graniterapids | sierraforest |
#   emeraldrapids | sapphirerapids | icelake | cascadelake | cooperlake |
#   skylake | unknown
# =============================================================================

model=$(lscpu | awk '/^Model:/{print $NF}')
family=$(lscpu | grep -v BIOS | awk '/^CPU family:/{print $NF}')
stepping=$(lscpu | awk '/^Stepping:/{print $NF}')

# ── CWF (Clearwater Forest) — primary target ──────────────────────────────────
if [[ $family -eq 6 ]] && [[ $model -eq 221 ]]; then
    if [[ $stepping -le 9 ]]; then
        echo "clearwaterforest"
        exit 0
    fi
fi

# ── DMR (Diamond Rapids) — family=19 ─────────────────────────────────────────
if [[ $family -eq 19 ]] && [[ $model -eq 1 ]]; then
    echo "diamondrapids"
    exit 0
fi

# ── GNR (Granite Rapids) ─────────────────────────────────────────────────────
if [[ $family -eq 6 ]] && [[ $model -eq 173 ]]; then
    if [[ $stepping -le 9 ]]; then
        echo "graniterapids"
        exit 0
    fi
fi

# ── SRF (Sierra Forest) ──────────────────────────────────────────────────────
if [[ $family -eq 6 ]] && [[ $model -eq 175 ]]; then
    if [[ $stepping -le 9 ]]; then
        echo "sierraforest"
        exit 0
    fi
fi

# ── EMR (Emerald Rapids) ─────────────────────────────────────────────────────
if [[ $family -eq 6 ]] && [[ $model -eq 207 ]]; then
    if [[ $stepping -le 9 ]]; then
        echo "emeraldrapids"
        exit 0
    fi
fi

# ── SPR (Sapphire Rapids) ────────────────────────────────────────────────────
if [[ $family -eq 6 ]] && [[ $model -eq 143 ]]; then
    if [[ $stepping -le 9 ]]; then
        echo "sapphirerapids"
        exit 0
    fi
fi

# ── ICX (Ice Lake) ───────────────────────────────────────────────────────────
if [[ $family -eq 6 ]] && [[ $model -eq 106 || $model -eq 108 ]]; then
    echo "icelake"
    exit 0
fi

# ── CLX / CPX / SKX (Cascade/Cooper/Sky Lake, model=85) ──────────────────────
if [[ $family -eq 6 ]] && [[ $model -eq 85 ]]; then
    if   [[ $stepping -ge 10 && $stepping -le 11 ]]; then echo "cooperlake"
    elif [[ $stepping -ge 5  && $stepping -le 7  ]]; then echo "cascadelake"
    elif [[ $stepping -ge 0  && $stepping -le 4  ]]; then echo "skylake"
    else echo "unknown"
    fi
    exit 0
fi

echo "unknown"
