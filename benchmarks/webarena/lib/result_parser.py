#!/usr/bin/env python3
"""
benchmarks/webarena/lib/result_parser.py

Parse WebArena evaluation output → structured result dict.

Mirrors pnpwls/{workload}/lib/results_manager.py pattern.
"""
import json
from pathlib import Path
from typing import Dict, Optional


def parse_webarena_results(results_dir: Path) -> Dict[str, str]:
    """Parse WebArena JSON result files in results_dir.

    Looks for *.json files containing 'success_rate' key (WebArena's
    standard output format).

    Args:
        results_dir: Path to the run-specific results directory.

    Returns:
        dict with keys: success_rate, num_success, num_total, tasks_failed
    """
    out = {
        "success_rate":   "0.0",
        "num_success":    "0",
        "num_total":      "0",
        "tasks_failed":   "0",
    }

    if not results_dir.exists():
        return out

    for jf in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text())
            if "success_rate" in data:
                out["success_rate"] = str(data.get("success_rate", 0.0))
                out["num_success"]  = str(data.get("num_success",  0))
                out["num_total"]    = str(data.get("num_total",    0))
                out["tasks_failed"] = str(
                    int(out["num_total"]) - int(out["num_success"])
                )
                break
        except Exception:
            continue

    return out
