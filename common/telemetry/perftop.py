#!/usr/bin/env python3
"""
perf-top/perf-record hotspot collector for steady-state telemetry windows.
"""

import glob
import json
import os
import re
import shutil
import signal
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional


class TelemetryStatus(Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class PerfTopCollector:
    """Collects fixed-window hotspot data using perf record/report."""

    def __init__(self, perf_binary: Optional[str] = None, output_dir: str = ".") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.perf_binary = self._find_binary(perf_binary)
        self.process: Optional[subprocess.Popen] = None
        self.data_file: Optional[Path] = None
        self.session_name: str = "perftop"
        self.duration_s: int = 150
        self.status = TelemetryStatus.NOT_STARTED

    def _find_binary(self, provided: Optional[str]) -> Optional[str]:
        if provided and os.path.isfile(provided):
            return provided

        which_perf = shutil.which("perf")
        if which_perf:
            return which_perf

        common_paths = ["/usr/bin/perf"]
        for path in common_paths:
            if os.path.isfile(path):
                return path

        for path in glob.glob("/usr/lib/linux-tools/*/perf"):
            if os.path.isfile(path):
                return path
        return None

    def is_available(self) -> bool:
        if not self.perf_binary:
            return False

        paranoid_path = Path("/proc/sys/kernel/perf_event_paranoid")
        try:
            paranoid = int(paranoid_path.read_text().strip())
            if paranoid > 1:
                print(
                    "[perftop] Warning: perf_event_paranoid > 1; profiling may need sudo "
                    "or sysctl adjustment. Attempting anyway."
                )
        except Exception:
            print("[perftop] Warning: unable to read perf_event_paranoid; attempting anyway.")
        return True

    def start_collection(self, session_name: str = "perftop", duration_s: int = 150) -> bool:
        if self.status == TelemetryStatus.RUNNING:
            print("[perftop] Already running")
            return False
        if not self.is_available():
            print("[perftop] perf not available — skipping")
            return False

        self.session_name = session_name
        self.duration_s = duration_s
        self.data_file = self.output_dir / f"perftop_{session_name}.data"
        cmd = [
            self.perf_binary,  # type: ignore[list-item]
            "record",
            "-a",
            "-g",
            "-o",
            str(self.data_file),
            "--",
            "sleep",
            str(duration_s),
        ]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.status = TelemetryStatus.RUNNING
            print(f"[perftop] Collection started → {self.data_file} (duration={duration_s}s)")
            return True
        except Exception as exc:
            print(f"[perftop] Failed to start collection: {exc}")
            self.status = TelemetryStatus.ERROR
            return False

    def stop_collection(self) -> bool:
        if not self.process:
            return False

        ok = True
        try:
            if self.process.poll() is None:
                try:
                    self.process.send_signal(signal.SIGINT)
                    self.process.wait(timeout=10)
                except Exception:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=10)
                    except Exception:
                        self.process.kill()
                        self.process.wait(timeout=5)
            else:
                self.process.wait(timeout=10)
            self.status = TelemetryStatus.STOPPED
        except Exception as exc:
            print(f"[perftop] Stop failed: {exc}")
            self.status = TelemetryStatus.ERROR
            ok = False
        return ok

    def process_report(self, top_n: int = 20) -> Optional[dict]:
        if not self.data_file or not self.data_file.exists():
            print("[perftop] No perf data file to process")
            return None
        if not self.perf_binary:
            print("[perftop] perf binary missing for report processing")
            return None

        report_cmd = [
            self.perf_binary,
            "report",
            "-i",
            str(self.data_file),
            "--stdio",
            "--sort=overhead,symbol",
            "-n",
            "--no-children",
        ]
        try:
            proc = subprocess.run(report_cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                stderr_text = (proc.stderr or "").strip()
                stderr_tail = stderr_text[-300:]
                truncated = "...(truncated) " if len(stderr_text) > 300 else ""
                print(f"[perftop] perf report failed (rc={proc.returncode}): {truncated}{stderr_tail}")
                return None
            if not proc.stdout.strip():
                print("[perftop] perf report output is empty")
                return None

            hotspots = []
            for line in proc.stdout.splitlines():
                match = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)%\s+(.+)$", line)
                if not match:
                    continue
                overhead_text = match.group(1).replace(",", ".")
                try:
                    overhead_pct = float(overhead_text)
                except ValueError:
                    continue
                rest = match.group(2).strip()
                # Expected --stdio format: "<pct>%  <command>  <shared-object>  <symbol>"
                # (columns separated by multiple spaces/tabs; symbol may contain spaces).
                columns = [c for c in re.split(r"(?:\s{2,}|\t+)", rest, maxsplit=2) if c]
                entry = {"overhead_pct": overhead_pct, "symbol": columns[-1] if columns else rest.strip()}
                if len(columns) >= 2:
                    entry["command"] = columns[0]
                if len(columns) >= 3:
                    entry["shared_object"] = columns[1]
                hotspots.append(entry)
                if len(hotspots) >= top_n:
                    break

            if not hotspots:
                print("[perftop] No hotspot entries parsed from perf report")
                return None

            summary = {
                "session_name": self.session_name,
                "duration_s": self.duration_s,
                "data_file": str(self.data_file),
                "top_n_requested": top_n,
                "top_n_actual": len(hotspots),
                "hotspots": hotspots,
            }
            summary_path = self.output_dir / "perftop_summary.json"
            summary_path.write_text(json.dumps(summary, indent=2))
            print(f"[perftop] Summary written → {summary_path}")
            return summary
        except FileNotFoundError:
            print("[perftop] perf report binary not found")
            return None
        except Exception as exc:
            print(f"[perftop] Failed to process report: {exc}")
            return None
