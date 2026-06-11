#!/usr/bin/env python3
"""
EMON Telemetry Collection Module
Manages Intel EMON (Event Monitor) data collection and EDP post-processing.

Mirrors pnpwls/common/telemetry/emon.py exactly — uses emon -collect-edp
and mpp.py post-processing.

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
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Dict


# ── Constants (mirror pnpwls defaults) ────────────────────────────────────────
DEFAULT_BEGIN_SAMPLE  = 700
DEFAULT_DIRTY_SAMPLES = 400

SEP_DIR_DEFAULT = "/opt/intel/sep"


class TelemetryStatus(Enum):
    NOT_STARTED = "not_started"
    RUNNING     = "running"
    STOPPED     = "stopped"
    ERROR       = "error"


class EmonCollector:
    """EMON data collector — wraps emon -collect-edp CLI via SEP/sep_vars.sh.
    
    Mirrors pnpwls implementation:
    1. Collect with: emon -collect-edp
    2. Stop with:    emon -stop
    3. Process with: python3 mpp.py (extracts metadata from EMON output)
    """

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

    # ── Collection lifecycle (pnpwls pattern) ──────────────────────────────────

    def start_collection(
        self,
        session_name: str = "emon_session",
        duration_s: Optional[int] = None,
    ) -> bool:
        """Start background EMON data collection with EDP preprocessing.

        Uses: emon -collect-edp (not -C event-list)

        Args:
            session_name: Label for the output file.
            duration_s:   If set, EMON auto-stops after this many seconds
                          (passed as ``-t <duration_s> -s 1``).
                          If None, collects until stop_collection() is called.
        """
        if self.status == TelemetryStatus.RUNNING:
            print("[emon] Already running")
            return False
        if not self.is_available():
            print("[emon] Not available — skipping")
            return False

        sep_vars    = self.sep_dir / "sep_vars.sh"
        output_file = self.output_dir / f"{session_name}.txt"
        self.output_file = output_file

        # pnpwls pattern: emon -collect-edp (auto-includes EDP preprocessing info)
        if duration_s is not None:
            sample_args = f"-t {int(duration_s)} -s 1"
            dur_label   = f"{duration_s}s"
        else:
            sample_args = ""
            dur_label   = "until stop()"

        cmd = (
            f"source {sep_vars} && "
            f"emon -collect-edp {sample_args} > {output_file} 2>&1"
        )
        try:
            self.process = subprocess.Popen(
                cmd, shell=True, executable="/bin/bash",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            self.status = TelemetryStatus.RUNNING
            print(f"[emon] Collection started → {output_file} (pid={self.process.pid}, duration={dur_label})")

            # If duration was given, spawn a watchdog so status reflects
            # when emon exits naturally.
            if duration_s is not None:
                def _watchdog():
                    self.process.wait()
                    if self.status == TelemetryStatus.RUNNING:
                        self.status = TelemetryStatus.STOPPED
                        print(f"[emon] Collection finished after {duration_s}s → {self.output_file}")
                threading.Thread(target=_watchdog, daemon=True).start()

            return True
        except Exception as exc:
            print(f"[emon] Failed to start: {exc}")
            if self.reload_drivers():
                return self.start_collection(session_name, duration_s)
            self.status = TelemetryStatus.ERROR
            return False

    def stop_collection(self) -> bool:
        """Stop EMON collection using emon -stop (pnpwls pattern)."""
        if self.status != TelemetryStatus.RUNNING or self.process is None:
            return False
        try:
            sep_vars = self.sep_dir / "sep_vars.sh"
            # Use emon -stop for graceful shutdown
            subprocess.run(
                f"source {sep_vars} && emon -stop",
                shell=True, executable="/bin/bash",
                capture_output=True, text=True, timeout=30
            )
            # Also clean up the process
            if self.process.poll() is None:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    self.process.wait(timeout=5)
                except Exception:
                    pass
            self.status = TelemetryStatus.STOPPED
            print(f"[emon] Collection stopped → {self.output_file}")
            return True
        except Exception as exc:
            print(f"[emon] Stop error: {exc}")
            self.status = TelemetryStatus.ERROR
            return False

    # ── Metadata extraction (pnpwls pattern) ────────────────────────────────────

    def _extract_edp_metadata(self, emon_file: Path) -> Dict[str, str]:
        """Extract EDP file paths from EMON output.
        
        Returns dict with keys: edp_xml_file, edp_chart_file, total_samples
        """
        metadata = {'edp_xml_file': '', 'edp_chart_file': '', 'total_samples': 0}
        try:
            with open(emon_file, 'r') as f:
                content = f.read()
            # Look for: "EDP metric file: /path/to/file.xml"
            m_xml = re.search(r'EDP metric file:\s*(.+)', content)
            if m_xml:
                metadata['edp_xml_file'] = m_xml.group(1).strip()
            # Look for: "EDP chart file: /path/to/file.xml"
            m_chart = re.search(r'EDP chart file:\s*(.+)', content)
            if m_chart:
                metadata['edp_chart_file'] = m_chart.group(1).strip()
            # Count samples
            metadata['total_samples'] = content.count('INST_RETIRED.ANY')
        except Exception as e:
            print(f"[emon] Error extracting metadata: {e}")
        return metadata

    # ── EDP post-processing (pnpwls pattern) ───────────────────────────────────

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
        Post-process an EMON file with mpp.py (EDP).

        pnpwls pattern:
        1. Extract EDP metadata from EMON output
        2. Call: python3 /opt/intel/sep/config/edp/pyedp/mpp.py -i <input> -f <chart> -m <xml> -o <output> --socket-view

        Returns the output directory on success, None on failure.
        """
        emon_file = emon_file or self.output_file
        if emon_file is None or not emon_file.exists():
            print(f"[emon] EDP: emon file not found: {emon_file}")
            return None

        # Extract metadata from EMON output
        metadata = self._extract_edp_metadata(emon_file)
        if not metadata['edp_xml_file'] or not metadata['edp_chart_file']:
            print(f"[emon] Could not extract EDP metadata from {emon_file}")
            return None

        # Calculate sample range
        total_samples = metadata['total_samples']
        if total_samples > 0:
            end_sample = max(begin_sample + 1, total_samples - dirty_samples)
        else:
            end_sample = 1000

        out_dir = self.output_dir / f"emon_{emon_file.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Build mpp.py command (pnpwls pattern)
        mpp_script = self.edp_dir / "pyedp" / "mpp.py"
        if not mpp_script.exists():
            print(f"[emon] mpp.py not found: {mpp_script}")
            return None

        edp_xml_path = self.edp_dir / metadata['edp_xml_file']
        edp_chart_path = self.edp_dir / metadata['edp_chart_file']

        # Build view flags
        view_flags = [f"--{v}" for v in views if v]

        cmd = [
            'python3', str(mpp_script),
            '-i', str(emon_file),
            '-f', str(edp_chart_path),
            '-m', str(edp_xml_path),
            '-o', str(out_dir / 'processed'),
            '-b', str(begin_sample),
            '-e', str(end_sample),
        ] + view_flags

        print(f"[emon] Running EDP post-processing …")
        print(f"[emon]   Command: {' '.join(cmd)}")
        
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if r.returncode == 0:
                print(f"[emon] EDP post-processing complete → {out_dir}")
                return out_dir
            else:
                print(f"[emon] EDP failed: {r.stderr[-500:]}")
                return None
        except subprocess.TimeoutExpired:
            print(f"[emon] EDP timed out")
            return None
        except Exception as e:
            print(f"[emon] EDP error: {e}")
            return None


# ── CSV readers ───────────────────────────────────────────────────────────────

def _read_emon_csv(csv_file: Path) -> Tuple[str, str]:
    """
    Parse a 2-row EMON CSV (header + data).
    Returns (header_csv_str, values_csv_str).
    """
    try:
        with open(csv_file) as f:
            lines = [ln.strip() for ln in f if ln.strip()]
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
