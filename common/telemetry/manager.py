#!/usr/bin/env python3
"""
Telemetry Manager — High-level facade for EMON + RAPL + SSMON + PTAT.

Usage:
    from common.telemetry import TelemetryManager

    tm = TelemetryManager(output_dir="results/run_001", platform="clearwaterforest")
    tm.start(session_name="cwf_8b_64c")

    # ... benchmark runs ...

    tm.stop()
    print(tm.rapl_mean)    # {domain: watts}
    print(tm.emon_ready)   # True if EDP processing succeeded
"""

from pathlib import Path
from typing import Dict, Optional
import threading
import time

from .emon  import EmonCollector
from .rapl  import RaplCollector
from .ssmon import SSMONCollector
from .ptat  import PTATCollector


class TelemetryManager:
    """Unified telemetry orchestrator for agentic AI benchmark runs."""

    def __init__(
        self,
        output_dir: str = ".",
        platform: str = "clearwaterforest",
        collect_emon: bool = True,
        collect_rapl: bool = True,
        collect_temp: bool = True,
        rapl_poll_interval_s: float = 5.0,
        emon_warmup_s: int = 0,
        emon_duration_s: Optional[int] = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.platform   = platform.lower()
        self.collect_emon = collect_emon
        self.collect_rapl = collect_rapl
        self.collect_temp = collect_temp
        self.emon_warmup_s   = emon_warmup_s
        self.emon_duration_s = emon_duration_s

        self.emon  = EmonCollector(output_dir=str(self.output_dir))
        self.rapl  = RaplCollector(poll_interval_s=rapl_poll_interval_s)

        # Temperature: SSMON for CWF/DMR/GNR/SRF; PTAT for older
        if SSMONCollector.is_platform_supported(self.platform):
            self.temp: object = SSMONCollector(output_dir=str(self.output_dir))
            self._temp_type = "ssmon"
        else:
            self.temp = PTATCollector(output_dir=str(self.output_dir))
            self._temp_type = "ptat"

        self._active: list = []
        self.rapl_mean: Dict[str, float] = {}
        self.emon_output_dir: Optional[Path] = None
        self.emon_ready = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, session_name: str = "telemetry") -> None:
        """Start all configured telemetry collectors.

        EMON obeys warmup/duration settings:
          emon_warmup_s   – sleep this many seconds after RAPL/temp start
                            before starting EMON (skip cold-start transient).
          emon_duration_s – EMON auto-stops after this many seconds; 0/None
                            means collect until stop() is called.
        """
        # RAPL and temperature start immediately — they are lightweight and
        # we want power/thermal data across the full run including warmup.
        if self.collect_rapl and self.rapl.is_available():
            self.rapl.start_polling()
            self._active.append("rapl")
            print(f"[telemetry] RAPL polling: {self.rapl.list_domains()}")

        if self.collect_temp:
            temp_ok = False
            if self._temp_type == "ssmon":
                temp_ok = self.temp.start_collection()  # type: ignore[attr-defined]
            else:
                temp_ok = self.temp.start_collection(session_name)  # type: ignore[attr-defined]
            if temp_ok:
                self._active.append("temp")
                print(f"[telemetry] Temperature ({self._temp_type}) started")

        # EMON: delay by warmup_s then collect for duration_s
        if self.collect_emon and self.emon.is_available():
            if self.emon_warmup_s > 0:
                print(f"[telemetry] EMON warmup: waiting {self.emon_warmup_s}s before starting collection …")
                self._active.append("emon")  # mark so stop() knows to handle it

                def _delayed_start():
                    time.sleep(self.emon_warmup_s)
                    if "emon" in self._active:  # still wanted (stop() not yet called)
                        ok = self.emon.start_collection(session_name, self.emon_duration_s)
                        if not ok:
                            self._active.remove("emon")
                            print("[telemetry] EMON failed to start after warmup")
                threading.Thread(target=_delayed_start, daemon=True).start()
            else:
                if self.emon.start_collection(session_name, self.emon_duration_s):
                    self._active.append("emon")
                    dur = f"{self.emon_duration_s}s" if self.emon_duration_s else "until stop()"
                    print(f"[telemetry] EMON started (duration={dur})")
                else:
                    print("[telemetry] EMON not available — skipping")

    def stop(
        self,
        process_emon: bool = True,
        sockets: int = 1,
        begin_sample: Optional[int] = None,
        dirty_samples: Optional[int] = None,
        views: Optional[tuple] = None,
        parallel_threads: Optional[int] = None,
        workload_log: Optional[Path] = None,
        workload_start_epoch: Optional[float] = None,
        workload_end_epoch: Optional[float] = None,
        start_marker: str = "",
        end_marker: str = "",
        archive_raw: bool = True,
    ) -> None:
        """Stop all collectors; optionally post-process EMON with EDP.

        Sample range (pnpwls pattern):
        - If workload_log + markers (or epoch times) are provided, the EMON sample
          range is auto-extracted from workload timestamps → EMON timestamps.
        - Otherwise, falls back to begin_sample / dirty_samples or emon.py defaults.
        """
        # Import here to avoid circular imports
        from .emon import (
            DEFAULT_BEGIN_SAMPLE,
            DEFAULT_DIRTY_SAMPLES,
            extract_emon_sample_range,
        )

        if "emon" in self._active:
            self.emon.stop_collection()
            if process_emon and self.emon.output_file and self.emon.output_file.exists():
                print(f"[telemetry] Processing EMON with EDP (platform={self.platform}, sockets={sockets})…")

                # Resolve sample range: try workload-log mapping first (pnpwls pattern)
                _begin = begin_sample if begin_sample is not None else DEFAULT_BEGIN_SAMPLE
                _dirty = dirty_samples if dirty_samples is not None else DEFAULT_DIRTY_SAMPLES

                if workload_log or workload_start_epoch is not None:
                    actual_start, actual_end = extract_emon_sample_range(
                        emon_file=self.emon.output_file,
                        workload_log=workload_log,
                        start_marker=start_marker,
                        end_marker=end_marker,
                        workload_start_epoch=workload_start_epoch,
                        workload_end_epoch=workload_end_epoch,
                    )
                    if actual_start > 0 and actual_end > actual_start:
                        print(f"[telemetry] Using workload-mapped EMON range: [{actual_start}, {actual_end}]")
                        # Override dirty_samples implicitly via passing begin/end via _begin
                        # process_emon_with_edp expects begin + dirty, so emit equivalent
                        # by treating actual_end as the new "non-dirty" boundary.
                        _begin = actual_start
                        # We can't pass explicit end; use a small dirty so process_emon
                        # computes end_sample = total - dirty. Convert:
                        try:
                            from .emon import count_emon_samples
                            _total = count_emon_samples(self.emon.output_file)
                            _dirty = max(0, _total - actual_end)
                        except Exception:
                            pass

                _views = views or ("socket-view",)
                self.emon_output_dir = self.emon.process_emon_with_edp(
                    platform=self.platform,
                    sockets=sockets,
                    begin_sample=_begin,
                    dirty_samples=_dirty,
                    views=_views,
                    parallel_threads=parallel_threads,
                    archive_raw=archive_raw,
                )
                if self.emon_output_dir:
                    self.emon_ready = True
                    print(f"[telemetry] EMON processing complete → {self.emon_output_dir}")
                else:
                    # EDP failed, but raw EMON data exists
                    self.emon_ready = False
                    print(f"[telemetry] EMON EDP post-processing failed, but raw data available: {self.emon.output_file}")
            else:
                print(f"[telemetry] EMON collection: process_emon={process_emon}, file_exists={self.emon.output_file and self.emon.output_file.exists()}")

        if "rapl" in self._active:
            self.rapl.stop_polling()
            self.rapl_mean = self.rapl.get_mean_power()
            print(f"[telemetry] RAPL mean power: {self.rapl_mean}")

        if "temp" in self._active:
            self.temp.stop_collection()  # type: ignore[attr-defined]

        self._active.clear()

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def pkg_power_w(self) -> float:
        """Aggregate package power across all sockets (watts)."""
        return sum(
            v for k, v in self.rapl_mean.items()
            if "package" in k.lower() or "pkg" in k.lower()
        )

    @property
    def dram_power_w(self) -> float:
        """Aggregate DRAM power across all sockets (watts)."""
        return sum(v for k, v in self.rapl_mean.items() if "dram" in k.lower())
