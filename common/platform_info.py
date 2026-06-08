#!/usr/bin/env python3
"""
Platform Detection Module
Maps CPU family/model/stepping → Intel platform codename.

Supported platforms:
  clearwaterforest (CWF)  family=6  model=221
  diamondrapids    (DMR)  family=19 model=1
  graniterapids    (GNR)  family=6  model=173
  sierraforest     (SRF)  family=6  model=175
  emeraldrapids    (EMR)  family=6  model=207
  sapphirerapids   (SPR)  family=6  model=143
  icelake          (ICX)  family=6  model=106 / 108
  cascadelake      (CLX)  family=6  model=85  stepping 5-7
  skylake          (SKX)  family=6  model=85  stepping 0-4

Usage:
    from common.platform_info import detect_platform, get_platform_info

    name = detect_platform()          # e.g. "clearwaterforest"
    info = get_platform_info()        # full dict
"""

import subprocess
import re
from typing import Dict, Optional


# ── Platform table ────────────────────────────────────────────────────────────
# Each entry: (family, model, stepping_min, stepping_max) -> codename
_PLATFORM_TABLE = [
    # CWF — primary target
    (6, 221, 0, 9,  "clearwaterforest"),
    # DMR
    (19, 1,  0, 9,  "diamondrapids"),
    # GNR
    (6, 173, 0, 9,  "graniterapids"),
    # SRF
    (6, 175, 0, 9,  "sierraforest"),
    # EMR
    (6, 207, 0, 9,  "emeraldrapids"),
    # SPR
    (6, 143, 0, 9,  "sapphirerapids"),
    # ICX (two model IDs)
    (6, 106, 0, 9,  "icelake"),
    (6, 108, 0, 9,  "icelake"),
    # CLX / SKX (same model, stepping distinguishes)
    (6, 85,  5, 7,  "cascadelake"),
    (6, 85,  10, 11, "cooperlake"),
    (6, 85,  0, 4,  "skylake"),
]

# Human-readable short names
_SHORT_NAME: Dict[str, str] = {
    "clearwaterforest": "CWF",
    "diamondrapids":    "DMR",
    "graniterapids":    "GNR",
    "sierraforest":     "SRF",
    "emeraldrapids":    "EMR",
    "sapphirerapids":   "SPR",
    "icelake":          "ICX",
    "cascadelake":      "CLX",
    "cooperlake":       "CPX",
    "skylake":          "SKX",
}

# EDP XML directory hints (used by process_emon.sh and telemetry/emon.py)
_EDP_SUBDIR: Dict[str, str] = {
    "clearwaterforest": "ClearwaterForest",
    "diamondrapids":    "DiamondRapids",
    "graniterapids":    "GraniteRapids",
    "sierraforest":     "SierraForest",
    "emeraldrapids":    "EmeraldRapids",
    "sapphirerapids":   "SapphireRapids",
    "icelake":          "IceLake",
    "cascadelake":      "CascadeLake",
    "cooperlake":       "CooperLake",
    "skylake":          "SkyLake",
}

# SSMON is the temperature tool for these platforms (vs PTAT for older)
_SSMON_PLATFORMS = {"clearwaterforest", "diamondrapids", "graniterapids", "sierraforest"}


def _lscpu_field(key: str) -> int:
    """Read a single integer field from lscpu."""
    try:
        result = subprocess.run(["lscpu"], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            line_key, _, value = line.partition(":")
            if line_key.strip() == key:
                # strip BIOS-related prefix noise in 'CPU family'
                value = re.sub(r".*\s", "", value).strip()
                return int(value)
    except Exception:
        pass
    return 0


def detect_platform() -> str:
    """
    Return the Intel platform codename string, e.g. 'clearwaterforest'.
    Returns 'unknown' if not recognised.
    """
    family   = _lscpu_field("CPU family")
    model    = _lscpu_field("Model")
    stepping = _lscpu_field("Stepping")

    for (f, m, s_min, s_max, name) in _PLATFORM_TABLE:
        if family == f and model == m and s_min <= stepping <= s_max:
            return name
    return "unknown"


def get_platform_info() -> Dict[str, str]:
    """
    Return a comprehensive platform info dict.

    Keys:
        codename, short_name, cpu_family, cpu_model, cpu_stepping,
        edp_subdir, use_ssmon, no_smt
    """
    codename = detect_platform()
    family   = _lscpu_field("CPU family")
    model    = _lscpu_field("Model")
    stepping = _lscpu_field("Stepping")

    # CWF and DMR have no HyperThreading
    no_smt_platforms = {"clearwaterforest", "diamondrapids"}

    return {
        "codename":   codename,
        "short_name": _SHORT_NAME.get(codename, "UNKN"),
        "cpu_family": str(family),
        "cpu_model":  str(model),
        "cpu_stepping": str(stepping),
        "edp_subdir": _EDP_SUBDIR.get(codename, codename),
        "use_ssmon":  str(codename in _SSMON_PLATFORMS).lower(),
        "no_smt":     str(codename in no_smt_platforms).lower(),
    }


__all__ = ["detect_platform", "get_platform_info"]
