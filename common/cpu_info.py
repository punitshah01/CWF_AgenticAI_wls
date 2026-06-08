#!/usr/bin/env python3
"""
CPU Information Module
Provides CPU topology and architecture information via lscpu.

Classes:
    CPUInfo: Reads lscpu once and exposes topology getters.
             CWF-specific: module topology, CBB count awareness.
"""

import subprocess
import re
from typing import Dict, List, Optional, Tuple


class CPUInfo:
    """
    CPU information parsed from lscpu.  Reads once at construction; all
    getters return cached values — no repeated subprocess calls.
    """

    def __init__(self) -> None:
        self._lscpu_data: Dict[str, str] = {}
        self._numa_node_cpus: Dict[int, str] = {}
        self._parse_lscpu()
        self._calculate_derived_values()

    # ── Parsing ──────────────────────────────────────────────────────────────

    def _parse_lscpu(self) -> None:
        try:
            result = subprocess.run(
                ["lscpu"], capture_output=True, text=True, check=True
            )
            for line in result.stdout.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    self._lscpu_data[key] = value
                    numa_match = re.match(r"NUMA node(\d+) CPU\(s\)", key)
                    if numa_match:
                        self._numa_node_cpus[int(numa_match.group(1))] = value
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"lscpu failed: {exc}") from exc

    def _calculate_derived_values(self) -> None:
        self._cores_per_socket  = self.get_cores_per_socket()
        self._total_sockets     = self.get_sockets()
        self._total_cores       = self._cores_per_socket * self._total_sockets
        self._total_numa_nodes  = self.get_numa_nodes()
        if self._total_numa_nodes > 0 and self._total_sockets > 0:
            self._numas_per_socket = self._total_numa_nodes // self._total_sockets
            self._cores_per_numa   = self._total_cores // self._total_numa_nodes
        else:
            self._numas_per_socket = 0
            self._cores_per_numa   = 0

    # ── Core topology ─────────────────────────────────────────────────────────

    def get_processors(self) -> int:
        """Total logical processors (including SMT threads)."""
        return int(self._lscpu_data.get("CPU(s)", "0"))

    def get_cores_per_socket(self) -> int:
        return int(self._lscpu_data.get("Core(s) per socket", "0"))

    def get_sockets(self) -> int:
        return int(self._lscpu_data.get("Socket(s)", "0"))

    def get_total_cores(self) -> int:
        return self._total_cores

    def get_threads_per_core(self) -> int:
        return int(self._lscpu_data.get("Thread(s) per core", "1"))

    # ── NUMA ──────────────────────────────────────────────────────────────────

    def get_numa_nodes(self) -> int:
        return int(self._lscpu_data.get("NUMA node(s)", "0"))

    def get_numas_per_socket(self) -> int:
        return self._numas_per_socket

    def get_cores_per_numa(self) -> int:
        return self._cores_per_numa

    def get_numa_node_cpus(self, node: int) -> str:
        """CPU list string for a NUMA node, e.g. '0-143'."""
        return self._numa_node_cpus.get(node, "")

    def get_all_numa_cpus(self) -> Dict[int, str]:
        return dict(self._numa_node_cpus)

    # ── CPU identity ──────────────────────────────────────────────────────────

    def get_cpu_family(self) -> int:
        raw = self._lscpu_data.get("CPU family", "0")
        # lscpu sometimes has "CPU family:" with BIOS prefix; strip it
        raw = re.sub(r".*\s", "", raw).strip()
        try:
            return int(raw)
        except ValueError:
            return 0

    def get_cpu_model(self) -> int:
        raw = self._lscpu_data.get("Model", "0")
        raw = re.sub(r".*\s", "", raw).strip()
        try:
            return int(raw)
        except ValueError:
            return 0

    def get_cpu_stepping(self) -> int:
        raw = self._lscpu_data.get("Stepping", "0")
        try:
            return int(raw)
        except ValueError:
            return 0

    def get_model_name(self) -> str:
        return self._lscpu_data.get("Model name", "Unknown")

    def get_cpu_max_mhz(self) -> str:
        return self._lscpu_data.get("CPU max MHz", "N/A")

    def get_cpu_min_mhz(self) -> str:
        return self._lscpu_data.get("CPU min MHz", "N/A")

    # ── CWF-specific helpers ──────────────────────────────────────────────────

    def is_cwf(self) -> bool:
        """True if running on Clearwater Forest (family=6, model=221)."""
        return self.get_cpu_family() == 6 and self.get_cpu_model() == 221

    def is_no_smt(self) -> bool:
        """True when threads_per_core == 1 (CWF and DMR never have SMT)."""
        return self.get_threads_per_core() == 1

    def get_module_count(self) -> int:
        """
        CWF: 4 cores per module. Returns total module count.
        Returns total_cores // 4 for CWF; -1 for unknown platforms.
        """
        if self.is_cwf():
            return max(1, self._total_cores // 4)
        return -1

    def get_topology_summary(self) -> str:
        """One-line topology string for logging."""
        return (
            f"{self._total_sockets}S x {self._cores_per_socket}C "
            f"x {self.get_threads_per_core()}T | "
            f"{self._total_numa_nodes} NUMA | "
            f"{self._total_cores} total cores"
        )

    # ── CPU range helpers (for numactl / taskset) ─────────────────────────────

    def get_cpu_range(self, start: int, count: int) -> str:
        """Return a CPU range string: 'start-(start+count-1)'."""
        end = start + count - 1
        return f"{start}-{end}"

    def get_inference_cpu_range(self, inference_cores: int) -> str:
        """Inference: cores 0 … inference_cores-1."""
        return self.get_cpu_range(0, inference_cores)

    def get_env_cpu_range(self, inference_cores: int, env_cores: int) -> str:
        """Environment: cores inference_cores … inference_cores+env_cores-1."""
        return self.get_cpu_range(inference_cores, env_cores)

    # ── Raw dict access ───────────────────────────────────────────────────────

    def get_raw(self, key: str, default: str = "N/A") -> str:
        return self._lscpu_data.get(key, default)

    def as_dict(self) -> Dict[str, str]:
        return dict(self._lscpu_data)
