#!/usr/bin/env python3
"""
RAPL Power Collection Module
Reads Intel RAPL (Running Average Power Limit) power counters from sysfs.

CWF Clearwater Forest:  package + DRAM domains via powercap sysfs.
This is the preferred lightweight power measurement for agentic workloads
(no PTAT/SSMON dependency).

Classes:
    RaplCollector  — snapshot and streaming RAPL power
"""

import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_POWERCAP_BASE = Path("/sys/class/powercap")
_INTEL_RAPL    = _POWERCAP_BASE / "intel-rapl"


def _rapl_domains() -> Dict[str, Path]:
    """Discover RAPL domains. Returns {name: energy_uj_path}."""
    domains: Dict[str, Path] = {}
    if not _INTEL_RAPL.exists():
        return domains
    for entry in sorted(_INTEL_RAPL.iterdir()):
        name_file = entry / "name"
        energy_file = entry / "energy_uj"
        if name_file.exists() and energy_file.exists():
            try:
                name = name_file.read_text().strip()
                # Prefix with package index for multi-socket clarity
                pkg_match = str(entry).split("intel-rapl:")[-1]
                domains[f"{name}_{pkg_match}"] = energy_file
            except Exception:
                pass
        # Sub-domains (dram, uncore, …)
        for sub in sorted(entry.iterdir()) if entry.is_dir() else []:
            sub_name_f  = sub / "name"
            sub_energy_f = sub / "energy_uj"
            if sub_name_f.exists() and sub_energy_f.exists():
                try:
                    sub_name = sub_name_f.read_text().strip()
                    pkg_match = str(sub).replace(str(_INTEL_RAPL) + "/", "").replace("/", "_")
                    domains[f"{sub_name}_{pkg_match}"] = sub_energy_f
                except Exception:
                    pass
    return domains


def _read_uj(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


class RaplCollector:
    """
    RAPL power collector.

    Usage (simple snapshot):
        r = RaplCollector()
        r.start()
        # ... workload runs ...
        power = r.stop()          # dict: {domain: watts}

    Usage (continuous polling):
        r = RaplCollector(poll_interval_s=1.0)
        r.start_polling()
        # ...
        samples = r.stop_polling()  # list of {domain: watts} dicts
    """

    def __init__(self, poll_interval_s: float = 5.0) -> None:
        self.poll_interval_s = poll_interval_s
        self._domains = _rapl_domains()
        self._t0: Optional[float] = None
        self._e0: Dict[str, int]  = {}
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._samples: List[Dict[str, float]] = []

    def is_available(self) -> bool:
        return bool(self._domains)

    def list_domains(self) -> List[str]:
        return list(self._domains.keys())

    # ── One-shot snapshot ─────────────────────────────────────────────────────

    def start(self) -> bool:
        """Record energy baseline."""
        if not self._domains:
            print("[rapl] No RAPL domains found (check powercap sysfs)")
            return False
        self._t0 = time.time()
        self._e0 = {}
        for name, path in self._domains.items():
            val = _read_uj(path)
            if val is not None:
                self._e0[name] = val
        return True

    def stop(self) -> Dict[str, float]:
        """
        Return average watts per domain since start().
        Returns empty dict if start() was not called.
        """
        if self._t0 is None or not self._e0:
            return {}
        t1 = time.time()
        elapsed = max(t1 - self._t0, 1e-6)
        result: Dict[str, float] = {}
        for name, path in self._domains.items():
            if name not in self._e0:
                continue
            e1 = _read_uj(path)
            if e1 is None:
                continue
            delta_uj = e1 - self._e0[name]
            # RAPL counters wrap at max_energy_range_uj
            if delta_uj < 0:
                try:
                    max_uj = int((path.parent / "max_energy_range_uj").read_text())
                    delta_uj += max_uj
                except Exception:
                    continue
            result[name] = round(delta_uj / elapsed / 1e6, 2)  # μJ/s → W
        return result

    # ── Continuous polling ────────────────────────────────────────────────────

    def start_polling(self) -> bool:
        if self._polling:
            return False
        if not self._domains:
            return False
        self._samples = []
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        return True

    def stop_polling(self) -> List[Dict[str, float]]:
        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=self.poll_interval_s * 3)
        return list(self._samples)

    def get_mean_power(self) -> Dict[str, float]:
        """Mean watts per domain from all polling samples."""
        if not self._samples:
            return {}
        totals: Dict[str, float] = {}
        counts: Dict[str, int]   = {}
        for sample in self._samples:
            for k, v in sample.items():
                totals[k] = totals.get(k, 0.0) + v
                counts[k] = counts.get(k, 0) + 1
        return {k: round(totals[k] / counts[k], 2) for k in totals}

    def _poll_loop(self) -> None:
        prev_e: Dict[str, int] = {}
        prev_t = time.time()
        # Initial read
        for name, path in self._domains.items():
            val = _read_uj(path)
            if val is not None:
                prev_e[name] = val
        time.sleep(self.poll_interval_s)
        while self._polling:
            curr_t = time.time()
            elapsed = max(curr_t - prev_t, 1e-6)
            sample: Dict[str, float] = {}
            curr_e: Dict[str, int] = {}
            for name, path in self._domains.items():
                val = _read_uj(path)
                if val is not None:
                    curr_e[name] = val
                    if name in prev_e:
                        delta = val - prev_e[name]
                        if delta < 0:
                            try:
                                max_uj = int(
                                    (path.parent / "max_energy_range_uj").read_text()
                                )
                                delta += max_uj
                            except Exception:
                                delta = 0
                        sample[name] = round(delta / elapsed / 1e6, 2)
            self._samples.append(sample)
            prev_e = curr_e
            prev_t = curr_t
            time.sleep(self.poll_interval_s)
