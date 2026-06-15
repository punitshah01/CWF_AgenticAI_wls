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
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Dict


# ── Constants (mirror pnpwls defaults) ────────────────────────────────────────
# pnpwls uses 700/400 for high-copy RATE workloads (>32 copies, long warmup).
# Agentic workloads are single-threaded LLM inference — more like SPEED/low-copy.
# Use conservative defaults: skip 50 warmup, 50 cooldown.
DEFAULT_BEGIN_SAMPLE  = 50
DEFAULT_DIRTY_SAMPLES = 50

# For reference if someone passes high-copy RATE style workloads:
RATE_HIGH_COPY_BEGIN  = 700
RATE_HIGH_COPY_DIRTY  = 400

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

    def _ensure_drivers_loaded(self) -> bool:
        """Check if SEP kernel drivers are loaded; auto-load if not."""
        r = subprocess.run(
            ["lsmod"], capture_output=True, text=True,
        )
        if "sepint" in r.stdout or "sep5" in r.stdout:
            return True
        # Drivers not loaded — try to load them
        print("[emon] SEP drivers not loaded, loading now …")
        return self.reload_drivers()

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
        if not self._ensure_drivers_loaded():
            print("[emon] Failed to load SEP drivers — EMON collection will be incomplete")
            # Continue anyway — some events may still work via software counters

        sep_vars    = self.sep_dir / "sep_vars.sh"
        output_file = self.output_dir / f"{session_name}.txt"
        self.output_file = output_file

        # pnpwls pattern: emon -collect-edp runs indefinitely until emon -stop.
        # The -t flag does NOT work with -collect-edp. We handle duration via a
        # timer thread that calls stop_collection() after duration_s seconds.
        dur_label = f"{duration_s}s" if duration_s else "until stop()"

        cmd = (
            f"source {sep_vars} && "
            f"emon -collect-edp > {output_file} 2>&1"
        )
        try:
            self.process = subprocess.Popen(
                cmd, shell=True, executable="/bin/bash",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )
            self.status = TelemetryStatus.RUNNING
            print(f"[emon] Collection started → {output_file} (pid={self.process.pid}, duration={dur_label})")

            # If duration was given, spawn a timer that calls emon -stop after N seconds.
            if duration_s is not None:
                def _auto_stop():
                    import time as _time
                    _time.sleep(duration_s)
                    if self.status == TelemetryStatus.RUNNING:
                        self.stop_collection()
                        print(f"[emon] Collection finished after {duration_s}s → {self.output_file}")
                threading.Thread(target=_auto_stop, daemon=True).start()

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
            try:
                subprocess.run(
                    f"source {sep_vars} && emon -stop",
                    shell=True, executable="/bin/bash",
                    capture_output=True, text=True, timeout=120,
                )
            except subprocess.TimeoutExpired:
                # emon -stop can occasionally hang while flushing output.
                # Continue with process-group termination to avoid blocking the run.
                print("[emon] emon -stop timed out after 120s, forcing process shutdown")
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
        parallel_threads: Optional[int] = None,
        archive_raw: bool = True,
    ) -> Optional[Path]:
        """
        Post-process an EMON file with mpp.py (EDP).

        pnpwls pattern:
        1. Extract EDP metadata from EMON output
        2. Call: python3 mpp.py -i <input> -f <chart> -m <xml> -o <output> -p <threads> --views
        3. Archive raw EMON .txt to .tar.gz (non-blocking)

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

        # Calculate sample range (pnpwls pattern)
        # EDP on CWF with 3570 events: each sample takes ~7-8s (full event group rotation).
        # A 180s collection yields ~24 samples. If total < begin+dirty, process all samples.
        total_samples = metadata['total_samples']
        if total_samples > (begin_sample + dirty_samples):
            end_sample = total_samples - dirty_samples
        elif total_samples > 0:
            # Too few samples for trimming — process all of them
            begin_sample = 1
            end_sample = total_samples
        else:
            begin_sample = 1
            end_sample = 1
        print(f"[emon] Samples: total={total_samples}, processing range [{begin_sample}, {end_sample}]")

        out_dir = self.output_dir / f"emon_{emon_file.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Build mpp.py command (pnpwls pattern)
        mpp_script = self.edp_dir / "pyedp" / "mpp.py"
        if not mpp_script.exists():
            print(f"[emon] mpp.py not found: {mpp_script}")
            return None

        # Use system python (/usr/bin/python3) for EDP — deps installed there,
        # venv python may lack packages and can't pip install (no network to pypi.org).
        _sys_python = "/usr/bin/python3"
        if not os.path.exists(_sys_python):
            _sys_python = "python3"  # fallback

        # Verify deps with system python; auto-install if missing (pnpwls: PIP_BREAK_SYSTEM_PACKAGES=1)
        _required = ["pandas", "numpy", "pytz", "defusedxml", "openpyxl", "xlsxwriter"]
        _missing = []
        for _mod in _required:
            _r = subprocess.run([_sys_python, "-c", f"import {_mod}"], capture_output=True, text=True)
            if _r.returncode != 0:
                _missing.append(_mod)
        if _missing:
            print(f"[emon] Installing missing EDP deps: {' '.join(_missing)}")
            _env = os.environ.copy()
            _env["PIP_BREAK_SYSTEM_PACKAGES"] = "1"
            _pip_cmd_base = [_sys_python, "-m", "pip", "install", "--quiet", "-U"]
            _success = False
            _inst = None
            for _proxy in ["http://proxy.intel.com:911", "http://proxy01.iind.intel.com:911", None]:
                _cmd = _pip_cmd_base + (["--proxy", _proxy] if _proxy else []) + _missing
                _inst = subprocess.run(_cmd, capture_output=True, text=True, env=_env)
                if _inst.returncode == 0:
                    _success = True
                    break
            if not _success:
                _stderr = _inst.stderr[-300:] if _inst else ""
                print(
                    "[emon] EDP skipped: failed to install required deps for mpp.py.\n"
                    f"[emon]   Missing: {' '.join(_missing)}\n"
                    f"[emon]   pip stderr: {_stderr}\n"
                    "[emon]   Fix manually with: /usr/bin/python3 -m pip install --proxy http://proxy.intel.com:911 -U "
                    + " ".join(_missing)
                )
                return None

        edp_xml_path = self.edp_dir / metadata['edp_xml_file']
        edp_chart_path = self.edp_dir / metadata['edp_chart_file']

        # Determine parallelism for mpp.py (pnpwls: num_cores * 3 // 4)
        if parallel_threads is None:
            try:
                parallel_threads = max(1, os.cpu_count() * 3 // 4)
            except Exception:
                parallel_threads = 48

        # Build view flags
        view_flags = [f"--{v}" for v in views if v]

        cmd = [
            _sys_python, str(mpp_script),
            '-i', str(emon_file),
            '-f', str(edp_chart_path),
            '-m', str(edp_xml_path),
            '-o', str(out_dir / 'processed'),
            '-b', str(begin_sample),
            '-e', str(end_sample),
            '-p', str(parallel_threads),
        ] + view_flags

        print("[emon] Running EDP post-processing …")
        print(f"[emon]   Command: {' '.join(cmd)}")

        try:
            # Stream output live (pnpwls pattern) so user sees progress
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                print(f"[emon/mpp] {line}", end='', flush=True)
            process.wait(timeout=600)

            if process.returncode == 0:
                print(f"[emon] EDP post-processing complete → {out_dir}")
                # Archive raw EMON file to save disk (pnpwls pattern)
                if archive_raw:
                    self._archive_raw_emon(emon_file)
                return out_dir
            else:
                print(f"[emon] EDP failed with exit code {process.returncode}")
                return None
        except subprocess.TimeoutExpired:
            process.kill()
            print("[emon] EDP timed out (600s)")
            return None
        except Exception as e:
            print(f"[emon] EDP error: {e}")
            return None

    def _archive_raw_emon(self, emon_file: Path, timeout: int = 180) -> None:
        """Compress raw EMON file (often 50-100MB+) to save disk. Non-blocking on failure."""
        if not emon_file.exists():
            return
        archive = emon_file.with_suffix('.txt.tar.gz')
        try:
            r = subprocess.run(
                f"tar czf {archive} -C {emon_file.parent} {emon_file.name}",
                shell=True, capture_output=True, text=True, timeout=timeout,
            )
            if r.returncode == 0:
                emon_file.unlink()
                print(f"[emon] Archived raw data → {archive.name}")
            else:
                print(f"[emon] Archive warning: tar failed ({r.returncode}), raw file kept")
        except subprocess.TimeoutExpired:
            print(f"[emon] Archive skipped: tar timed out ({timeout}s)")
        except Exception as e:
            print(f"[emon] Archive skipped: {e}")


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


# ── Sample range extraction (pnpwls pattern) ──────────────────────────────────

def count_emon_samples(emon_file: Path) -> int:
    """Count total EMON samples in a raw .txt file by counting INST_RETIRED.ANY occurrences."""
    try:
        with open(emon_file, 'r') as f:
            return sum(1 for line in f if 'INST_RETIRED.ANY' in line)
    except Exception:
        return 0


def extract_emon_sample_range(
    emon_file: Path,
    workload_log: Optional[Path] = None,
    start_marker: str = "",
    end_marker: str = "",
    workload_start_epoch: Optional[float] = None,
    workload_end_epoch: Optional[float] = None,
) -> Tuple[int, int]:
    """
    Map a workload's start/end time to EMON sample indices.

    pnpwls pattern (run_spec.py: extract_emon_sample_range):
    - Parse workload log for start/end timestamps (epoch or marker-based)
    - Parse EMON file timestamps (MM/DD/YYYY HH:MM:SS.fraction format)
    - Find first sample at/after workload_start, last sample at/before workload_end

    Args:
        emon_file: Path to raw EMON .txt file
        workload_log: Optional log file to extract timestamps from
        start_marker/end_marker: Regex patterns in workload_log; group 1 = epoch seconds
        workload_start_epoch/workload_end_epoch: Direct epoch overrides (if log parsing not used)

    Returns:
        (start_sample, end_sample) — both 1-based; (0, 0) if extraction failed.
    """
    try:
        import time as _time

        start_ts = workload_start_epoch
        end_ts = workload_end_epoch

        # Try parsing markers from workload log if epoch values not given
        if workload_log and workload_log.exists() and (start_ts is None or end_ts is None):
            content = workload_log.read_text(errors="ignore")
            if start_marker and start_ts is None:
                m = re.search(start_marker, content)
                if m:
                    try:
                        start_ts = float(m.group(1))
                    except (ValueError, IndexError):
                        pass
            if end_marker and end_ts is None:
                m = re.search(end_marker, content)
                if m:
                    try:
                        end_ts = float(m.group(1))
                    except (ValueError, IndexError):
                        pass

        if start_ts is None or end_ts is None:
            return (0, 0)

        # Parse EMON file for per-sample timestamps
        if not emon_file.exists():
            return (0, 0)

        ts_re = re.compile(r'(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\.(\d+)')
        start_sample = 0
        end_sample = 0
        sample_num = 0

        with open(emon_file, 'r') as f:
            for line in f:
                # Each sample is marked by INST_RETIRED.ANY appearing once per rotation
                if 'INST_RETIRED.ANY' in line:
                    sample_num += 1
                    continue
                m = ts_re.match(line)
                if not m:
                    continue
                mo, dy, yr, hh, mm, ss, frac = m.groups()
                try:
                    ts = _time.mktime(_time.strptime(
                        f"{yr} {mo} {dy} {hh} {mm} {ss}", "%Y %m %d %H %M %S"
                    )) + float(f"0.{frac}")
                except Exception:
                    continue
                if start_sample == 0 and ts >= start_ts:
                    start_sample = max(1, sample_num)
                if ts <= end_ts:
                    end_sample = max(1, sample_num)

        if start_sample > 0 and end_sample >= start_sample:
            return (start_sample, end_sample)
        return (0, 0)
    except Exception as e:
        print(f"[emon] extract_emon_sample_range error: {e}")
        return (0, 0)
