#!/usr/bin/env python3
"""
EMON Telemetry Collection Module
Manages Intel EMON (Event Monitor) data collection and EDP post-processing.

Same API contract as pnpwls/common/telemetry/emon.py, extended for CWF.

Classes:
    EmonCollector  — start/stop/process EMON collection

Functions:
    read_emon_socket_view  — parse socket-view CSV → (header, values)
    read_emon_core_view    — parse core-view CSV → (header, values)
    read_emon_system_view  — parse system-view CSV → (header, values)
"""

import os
import re
import signal
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple


# ── Constants (mirror pnpwls defaults) ────────────────────────────────────────
DEFAULT_BEGIN_SAMPLE  = 700
DEFAULT_DIRTY_SAMPLES = 400
LOW_COPY_BEGIN_SAMPLE  = 50
LOW_COPY_DIRTY_SAMPLES = 50
SPEED_BEGIN_SAMPLE     = 50
SPEED_DIRTY_SAMPLES    = 50
LOW_COPY_THRESHOLD     = 32

SEP_DIR_DEFAULT = "/opt/intel/sep"


class TelemetryStatus(Enum):
    NOT_STARTED = "not_started"
    RUNNING     = "running"
    STOPPED     = "stopped"
    ERROR       = "error"


class EmonCollector:
    """EMON data collector — wraps emon CLI via SEP/sep_vars.sh."""

    def __init__(self, sep_dir: str = SEP_DIR_DEFAULT, output_dir: str = ".") -> None:
        self.sep_dir    = Path(sep_dir)
        self.edp_dir    = self.sep_dir / "config" / "edp"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_file: Optional[Path] = None
        self.process: Optional[subprocess.Popen] = None
        self.status = TelemetryStatus.NOT_STARTED
        self._check_installation()

    # ── Installation check ────────────────────────────────────────────────────

    def _check_installation(self) -> bool:
        sep_vars = self.sep_dir / "sep_vars.sh"
        if not sep_vars.exists():
            self.status = TelemetryStatus.ERROR
            return False
        try:
            r = subprocess.run(
                f"source {sep_vars} && which emon",
                shell=True, executable="/bin/bash",
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                return True
        except Exception:
            pass
        self.status = TelemetryStatus.ERROR
        return False

    def is_available(self) -> bool:
        return self._check_installation()

    # ── Driver management ─────────────────────────────────────────────────────

    def reload_drivers(self) -> bool:
        """Reload SEP kernel drivers (insmod-sep / rmmod-sep)."""
        sepsrc = self.sep_dir / "sepdk" / "src"
        if not sepsrc.exists():
            print(f"[emon] SEPDK src not found: {sepsrc}")
            return False
        print("[emon] Reloading SEP drivers …")
        for script, descr in [("rmmod-sep", "rmmod"), ("insmod-sep", "insmod")]:
            s = sepsrc / script
            if s.exists():
                r = subprocess.run(["sudo", str(s)], capture_output=True,
                                   text=True, timeout=30)
                if r.returncode != 0:
                    print(f"[emon] {descr} returned {r.returncode}: {r.stderr}")
                    if descr == "insmod":
                        return False
        return True

    # ── Collection lifecycle ──────────────────────────────────────────────────

    def start_collection(self, session_name: str = "emon_session") -> bool:
        """Start background EMON data collection."""
        if self.status == TelemetryStatus.RUNNING:
            print("[emon] Already running")
            return False
        if not self.is_available():
            print("[emon] Not available — skipping")
            return False

        sep_vars    = self.sep_dir / "sep_vars.sh"
        output_file = self.output_dir / f"{session_name}.txt"
        self.output_file = output_file

        cmd = (
            f"source {sep_vars} && "
            f"emon -collect -f {output_file} -t 100 -s 1"
        )
        try:
            self.process = subprocess.Popen(
                cmd, shell=True, executable="/bin/bash",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            self.status = TelemetryStatus.RUNNING
            print(f"[emon] Collection started → {output_file} (pid={self.process.pid})")
            return True
        except Exception as exc:
            print(f"[emon] Failed to start: {exc}")
            if self.reload_drivers():
                return self.start_collection(session_name)
            self.status = TelemetryStatus.ERROR
            return False

    def stop_collection(self) -> bool:
        """Stop EMON collection."""
        if self.status != TelemetryStatus.RUNNING or self.process is None:
            return False
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait(timeout=30)
            self.status = TelemetryStatus.STOPPED
            print(f"[emon] Collection stopped → {self.output_file}")
            return True
        except Exception as exc:
            print(f"[emon] Stop error: {exc}")
            self.status = TelemetryStatus.ERROR
            return False

    # ── EDP post-processing ───────────────────────────────────────────────────

    def process_emon_with_edp(
        self,
        emon_file: Optional[Path] = None,
        platform: str = "clearwaterforest",
        sockets: int = 1,
        begin_sample: int = DEFAULT_BEGIN_SAMPLE,
        dirty_samples: int = DEFAULT_DIRTY_SAMPLES,
        views: Tuple[str, ...] = ("socket-view",),
    ) -> Optional[Path]:
        """
        Post-process an EMON file with EDP (pyedp or jruby edp.rb).

        Returns the output directory on success, None on failure.
        """
        emon_file = emon_file or self.output_file
        if emon_file is None or not emon_file.exists():
            print(f"[emon] EDP: emon file not found: {emon_file}")
            return None

        # Locate edp XML
        from common.platform_info import _EDP_SUBDIR  # lazy import
        edp_subdir = _EDP_SUBDIR.get(platform, platform.title())
        xml_pattern = (
            f"{self.edp_dir}/Architecture*/{edp_subdir}/"
            f"*{sockets}s*.xml"
        )

        # Count samples
        try:
            r = subprocess.run(
                f"grep -c INST_RETIRED.ANY {emon_file}",
                shell=True, capture_output=True, text=True,
            )
            total_samples = int(r.stdout.strip())
            stop_sample   = max(1, total_samples - dirty_samples)
        except Exception:
            begin_sample = 50
            stop_sample  = 1000

        out_dir = self.output_dir / f"emon_{emon_file.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Try pyedp first, fall back to jruby edp.rb
        pyedp = self.edp_dir / "pyedp" / "pyedp.py"
        edp_rb = self.edp_dir / "edp.rb"

        view_flags = " ".join(f"--{v}" for v in views)

        if pyedp.exists():
            cmd = (
                f"source {self.sep_dir}/sep_vars.sh && "
                f"python3 {pyedp} "
                f"-i {emon_file} "
                f"-b {begin_sample} -e {stop_sample} "
                f"{view_flags} "
                f"-o {out_dir}/processed_metrics"
            )
        elif edp_rb.exists():
            cmd = (
                f"source {self.sep_dir}/sep_vars.sh && "
                f"jruby {edp_rb} "
                f"-i {emon_file} -m {xml_pattern} "
                f"--socket-view "
                f"-o {out_dir}/processed_metrics "
                f"-b {begin_sample} -e {stop_sample}"
            )
        else:
            print("[emon] Neither pyedp nor edp.rb found")
            return None

        print(f"[emon] Running EDP … output → {out_dir}")
        r = subprocess.run(cmd, shell=True, executable="/bin/bash",
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[emon] EDP failed: {r.stderr[-500:]}")
            return None

        return out_dir


# ── CSV readers ───────────────────────────────────────────────────────────────

def _read_emon_csv(csv_file: Path) -> Tuple[str, str]:
    """
    Parse a 2-row EMON CSV (header + data).
    Returns (header_csv_str, values_csv_str).
    """
    try:
        with open(csv_file) as f:
            lines = [l.strip() for l in f if l.strip()]
        if len(lines) < 2:
            return "", ""
        header = lines[0]
        values_parts = []
        for v in lines[1].split(","):
            v = v.strip()
            try:
                fv = float(v)
                values_parts.append(f"{fv:.5f}" if fv < 1 else f"{fv:.2f}")
            except ValueError:
                values_parts.append(v)
        return header, ",".join(values_parts)
    except Exception as exc:
        print(f"[emon] CSV read error: {exc}")
        return "", ""


def read_emon_socket_view(emon_csv: Path) -> Tuple[str, str]:
    """Parse __mpp_socket_view_summary.csv → (header, values)."""
    return _read_emon_csv(emon_csv)


def read_emon_core_view(emon_csv: Path) -> Tuple[str, str]:
    """Parse __mpp_core_view_summary.csv → (header, values)."""
    return _read_emon_csv(emon_csv)


def read_emon_system_view(emon_csv: Path) -> Tuple[str, str]:
    """Parse __mpp_system_view_summary.csv → (header, values)."""
    return _read_emon_csv(emon_csv)


def get_emon_csv_header(emon_csv: Path) -> str:
    """Return comma-separated header string from an EMON CSV."""
    try:
        with open(emon_csv) as f:
            return f.readline().strip()
    except Exception:
        return ""
