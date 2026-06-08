#!/usr/bin/env python3
"""
PTAT Temperature Collection Module
Intel Platform Telemetry and Analytics Tool — for older platforms (pre-DMR/CWF).
"""

import os
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional


class TelemetryStatus(Enum):
    NOT_STARTED = "not_started"
    RUNNING     = "running"
    STOPPED     = "stopped"
    ERROR       = "error"


class PTATCollector:
    """PTAT temperature collector for older Intel platforms."""

    def __init__(self, ptat_binary: Optional[str] = None, output_dir: str = ".") -> None:
        self.output_dir   = Path(output_dir)
        self.ptat_binary  = self._find_binary(ptat_binary)
        self.process: Optional[subprocess.Popen] = None
        self.status = TelemetryStatus.NOT_STARTED
        self.output_files: List[Path] = []

    def _find_binary(self, provided: Optional[str]) -> Optional[str]:
        if provided and os.path.isfile(provided):
            return provided
        for path in [
            os.path.expanduser("~/devtools/ptat/ptat"),
            "/usr/local/bin/ptat",
            "/opt/intel/ptat/ptat",
        ]:
            if os.path.isfile(path):
                return path
        return None

    def is_available(self) -> bool:
        return self.ptat_binary is not None

    def start_collection(
        self,
        session_name: str = "ptat_session",
        filter_val: str = "0x4",
    ) -> bool:
        if not self.is_available():
            return False
        out_csv = self.output_dir / f"{session_name}.csv"
        out_log = self.output_dir / f"{session_name}.log"
        self.output_files = [out_csv, out_log]
        cmd = [
            self.ptat_binary,
            "-filter", filter_val,
            "-csv", str(out_csv),
            "-log", str(out_log),
            "-q", "-y", "-id",
        ]
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.status = TelemetryStatus.RUNNING
            return True
        except Exception as exc:
            print(f"[ptat] Start failed: {exc}")
            self.status = TelemetryStatus.ERROR
            return False

    def stop_collection(self) -> bool:
        if self.process and self.status == TelemetryStatus.RUNNING:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except Exception:
                self.process.kill()
            self.status = TelemetryStatus.STOPPED
            return True
        return False
