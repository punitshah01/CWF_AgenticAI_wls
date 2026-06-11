#!/usr/bin/env python3
"""
TemperatureMonitor — Platform-aware temperature monitoring facade.

Mirrors pnpwls/common/telemetry/temperature.py.

Automatically selects SSMON or PTAT based on platform string.
SSMON is used for CWF, DMR, GNR, SRF (modern platforms).
PTAT is used for legacy platforms (SPR and older).

Usage:
    from common.telemetry import TemperatureMonitor

    monitor = TemperatureMonitor(platform="clearwaterforest",
                                  output_dir="results/run/telemetry")
    monitor.start("session_label")
    # ... workload runs ...
    monitor.stop()
    avg_temp = monitor.get_average_temperature()
"""

from pathlib import Path
from typing import Optional

from .ssmon import SSMONCollector
from .ptat  import PTATCollector


# Platforms where SSMON is the correct temperature collector.
# All others fall back to PTAT.
_SSMON_PLATFORMS = {
    "clearwaterforest",
    "diamondrapids",
    "graniterapids",
    "sierraforest",
    "emeraldrapids",
    "granite",
    "cwf",
    "dmr",
    "gnr",
    "srf",
    "emr",
}


class TemperatureMonitor:
    """Platform-aware temperature monitoring facade.

    Wraps SSMONCollector or PTATCollector based on the detected platform.
    Exposes a unified start/stop/get_average_temperature() interface
    identical to pnpwls.
    """

    def __init__(self, platform: str = "clearwaterforest",
                 output_dir: str = ".") -> None:
        self.platform   = platform.lower().replace(" ", "")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if SSMONCollector.is_platform_supported(self.platform):
            self._collector: object = SSMONCollector(output_dir=str(self.output_dir))
            self._backend = "ssmon"
        else:
            self._collector = PTATCollector(output_dir=str(self.output_dir))
            self._backend = "ptat"

        self._running = False

    @property
    def backend(self) -> str:
        """Which backend is active: 'ssmon' or 'ptat'."""
        return self._backend

    def is_available(self) -> bool:
        """Return True if the chosen backend can start successfully."""
        if self._backend == "ssmon":
            return self._collector.is_available()  # type: ignore[attr-defined]
        else:
            return self._collector.is_available()  # type: ignore[attr-defined]

    def start(self, session_name: str = "temp_session") -> bool:
        """Start temperature collection.

        Args:
            session_name: Label used for output file naming.

        Returns:
            True if collection started successfully.
        """
        if self._running:
            return True

        if self._backend == "ssmon":
            ok = self._collector.start_collection()  # type: ignore[attr-defined]
        else:
            ok = self._collector.start_collection(session_name)  # type: ignore[attr-defined]

        if ok:
            self._running = True
        return ok

    def stop(self, session_name: str = "temp_session") -> bool:
        """Stop temperature collection and rename output file.

        Args:
            session_name: Used to rename output file for identification.

        Returns:
            True if stopped successfully.
        """
        if not self._running:
            return False

        self._collector.stop_collection()  # type: ignore[attr-defined]

        if hasattr(self._collector, 'rename_output'):
            prefix = "ssmon" if self._backend == "ssmon" else "ptatmon"
            self._collector.rename_output(f"{prefix}_{session_name}")  # type: ignore[attr-defined]

        self._running = False
        return True

    def get_average_temperature(self) -> Optional[float]:
        """Return the mean temperature (°C) over the collection period.

        Returns None if no data is available.
        """
        if hasattr(self._collector, 'calculate_average_temp'):
            return self._collector.calculate_average_temp()  # type: ignore[attr-defined]
        return None

    def get_status(self) -> dict:
        """Return current status dict."""
        return {
            "backend":  self._backend,
            "running":  self._running,
            "platform": self.platform,
        }
