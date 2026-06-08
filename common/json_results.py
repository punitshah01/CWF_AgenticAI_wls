#!/usr/bin/env python3
"""
JSON Results Writer — Structured per-run output (same contract as pnpwls).

Usage:
    from common.json_results import ResultsJsonWriter

    writer = ResultsJsonWriter(output_dir=Path("results/swebench"), run_id="cwf_8b_64c")

    writer.add_row(
        common_data=common_data,         # OrderedDict with all fields
        emon_data="3.59,2.20,...",        # comma-sep socket-view EMON (or "")
        emon_header="metric_CPU_freq,...",
        emon_core_data="...",            # optional core-view
        emon_core_header="...",
        rapl_data={"pkg_w": 185.4, "dram_w": 42.1},  # RAPL power dict (CWF)
    )

    writer.save()                        # write results.json
"""

import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional


# Keys classified as "system" metadata (not workload results)
_SYSTEM_KEYS = {
    "run_id", "hostname", "experiment_name", "platform",
    "cpu_model", "cpu_family", "cpu_model_num", "cpu_stepping",
    "cpu_sockets", "cores_per_socket", "threads_per_core",
    "total_cores", "numa_nodes", "numa_node_str", "cpu_max_mhz",
    "os_release", "kernel", "bios_version", "microcode", "qdf",
    "memory_total_gb", "memory_speed", "dimm_config", "tdp_pl1_watts",
    "cpu_governor", "thp_enabled", "thp_defrag", "numa_balancing",
    "nmi_watchdog", "cstates_enabled", "selinux", "irqbalance_status",
    "cmdline",
}


class ResultsJsonWriter:
    """Accumulates result rows and writes results.json to output_dir."""

    def __init__(self, output_dir: Path, run_id: str = "") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._rows: List[Dict] = []

    def add_row(
        self,
        common_data: OrderedDict,
        emon_data: str = "",
        emon_header: str = "",
        emon_core_data: str = "",
        emon_core_header: str = "",
        emon_system_data: str = "",
        emon_system_header: str = "",
        rapl_data: Optional[Dict[str, float]] = None,
    ) -> None:
        """Add one result row."""
        system  = {k: v for k, v in common_data.items() if k in _SYSTEM_KEYS}
        results = {k: v for k, v in common_data.items() if k not in _SYSTEM_KEYS}

        # EMON socket-view
        emon_dict: Dict = {}
        if emon_data and emon_header:
            headers = [h.strip() for h in emon_header.split(",")]
            values  = [v.strip() for v in emon_data.split(",")]
            for h, v in zip(headers, values):
                if h:
                    try:
                        emon_dict[h] = float(v)
                    except ValueError:
                        emon_dict[h] = v

        # EMON core-view
        emon_core_dict: Dict = {}
        if emon_core_data and emon_core_header:
            headers = [h.strip() for h in emon_core_header.split(",")]
            values  = [v.strip() for v in emon_core_data.split(",")]
            for h, v in zip(headers, values):
                if h:
                    try:
                        emon_core_dict[h] = float(v)
                    except ValueError:
                        emon_core_dict[h] = v

        row = {
            "system":       system,
            "results":      results,
            "emon":         emon_dict,
            "emon_core":    emon_core_dict,
            "rapl":         rapl_data or {},
        }
        self._rows.append(row)

    def save(self) -> Path:
        """Write all accumulated rows to results.json."""
        out_file = self.output_dir / "results.json"
        payload = {
            "run_id":  self.run_id,
            "rows":    self._rows,
        }
        with open(out_file, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"[json_results] Saved {len(self._rows)} rows to {out_file}")
        return out_file
