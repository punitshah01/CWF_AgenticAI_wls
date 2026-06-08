#!/usr/bin/env python3
"""
SSMON Temperature Collection Module
Supports newer platforms: Diamond Rapids and Clearwater Forest.
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


class SSMONCollector:
    """SSMON temperature collector for DMR and CWF."""

    SUPPORTED_PLATFORMS = ["diamondrapids", "clearwaterforest"]

    def __init__(self, ssmon_binary: Optional[str] = None, output_dir: str = ".") -> None:
        self.output_dir   = Path(output_dir)
        self.ssmon_binary = self._find_binary(ssmon_binary)
        self.process: Optional[subprocess.Popen] = None
        self.status = TelemetryStatus.NOT_STARTED
        self.output_prefix = "ssmon_log"

    def _find_binary(self, provided: Optional[str]) -> Optional[str]:
        if provided and os.path.isfile(provided):
            return provided
        for path in [
            os.path.expanduser("~/devtools/ssmon/ssmon"),
            "/usr/local/bin/ssmon",
            "/opt/intel/ssmon/ssmon",
        ]:
            if os.path.isfile(path):
                return path
        return None

    @classmethod
    def is_platform_supported(cls, platform: str) -> bool:
        return platform.lower() in cls.SUPPORTED_PLATFORMS

    def is_available(self) -> bool:
        return self.ssmon_binary is not None

    def start_collection(
        self,
        config_file: Optional[str] = None,
        duration_hours: int = 7,
    ) -> bool:
        if not self.is_available():
            return False
        out = self.output_dir / self.output_prefix
        cmd = [self.ssmon_binary, "-o", str(out)]
        if config_file:
            cmd += ["-c", config_file]
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.status = TelemetryStatus.RUNNING
            return True
        except Exception as exc:
            print(f"[ssmon] Start failed: {exc}")
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
