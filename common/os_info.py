#!/usr/bin/env python3
"""
Operating System Information Module
Provides BIOS, microcode, kernel, memory, and system-configuration details.

All methods read fresh from the system (no caching) to ensure live state.
"""

import subprocess
import re
from typing import List


class OSInfo:
    """
    OS and hardware configuration information.
    All reads are live (no caching).
    """

    def __init__(self) -> None:
        pass

    def _run(self, cmd: List[str], shell: bool = False) -> str:
        try:
            if shell:
                r = subprocess.run(" ".join(cmd), shell=True, executable="/bin/bash",
                                   capture_output=True, text=True, check=True)
            else:
                r = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return r.stdout.strip()
        except Exception:
            return "N/A"

    # ── BIOS / firmware ───────────────────────────────────────────────────────

    def get_bios_version(self) -> str:
        out = self._run(["sudo", "dmidecode", "-t", "bios"])
        for line in out.splitlines():
            if "Version:" in line:
                return line.split("Version:", 1)[1].strip()
        return "N/A"

    def get_bios_date(self) -> str:
        out = self._run(["sudo", "dmidecode", "-t", "bios"])
        for line in out.splitlines():
            if "Release Date:" in line:
                return line.split("Release Date:", 1)[1].strip()
        return "N/A"

    # ── Microcode ─────────────────────────────────────────────────────────────

    def get_microcode(self) -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "microcode" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "N/A"

    # ── OS / Kernel ───────────────────────────────────────────────────────────

    def get_os_pretty_name(self) -> str:
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return "N/A"

    def get_kernel(self) -> str:
        return self._run(["uname", "-r"])

    # ── Memory ────────────────────────────────────────────────────────────────

    def get_total_memory_gb(self) -> str:
        out = self._run(["free", "-g"])
        for line in out.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                return parts[1] if len(parts) > 1 else "N/A"
        return "N/A"

    def get_memory_speed(self) -> str:
        out = self._run(["sudo", "dmidecode", "-t", "memory"])
        speeds = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Speed:") and "MT/s" in line:
                val = line.split(":", 1)[1].strip()
                if val not in speeds and val != "Unknown":
                    speeds.append(val)
        return speeds[0] if speeds else "N/A"

    def get_dimm_config(self) -> str:
        """Return DIMM slot count / populated count string e.g. '12/12'."""
        out = self._run(["sudo", "dmidecode", "-t", "memory"])
        total = out.count("Memory Device")
        populated = out.count("Size: ") - out.count("Size: No Module Installed")
        if total:
            return f"{populated}/{total}"
        return "N/A"

    # ── CPU governor / power ──────────────────────────────────────────────────

    def get_cpu_governor(self) -> str:
        try:
            with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
                return f.read().strip()
        except Exception:
            pass
        return "N/A"

    def get_thp_enabled(self) -> str:
        try:
            with open("/sys/kernel/mm/transparent_hugepage/enabled") as f:
                content = f.read()
                match = re.search(r"\[(\w+)\]", content)
                return match.group(1) if match else content.strip()
        except Exception:
            return "N/A"

    def get_thp_defrag(self) -> str:
        try:
            with open("/sys/kernel/mm/transparent_hugepage/defrag") as f:
                content = f.read()
                match = re.search(r"\[(\w+)\]", content)
                return match.group(1) if match else content.strip()
        except Exception:
            return "N/A"

    def get_numa_balancing(self) -> str:
        try:
            with open("/proc/sys/kernel/numa_balancing") as f:
                return f.read().strip()
        except Exception:
            return "N/A"

    # ── NMI watchdog ─────────────────────────────────────────────────────────

    def get_nmi_watchdog(self) -> str:
        try:
            with open("/proc/sys/kernel/nmi_watchdog") as f:
                return f.read().strip()
        except Exception:
            return "N/A"

    # ── cstates ──────────────────────────────────────────────────────────────

    def get_cstates_enabled(self) -> str:
        try:
            with open("/sys/module/intel_idle/parameters/max_cstate") as f:
                return f.read().strip()
        except Exception:
            return "N/A"

    # ── SELinux ───────────────────────────────────────────────────────────────

    def get_selinux(self) -> str:
        return self._run(["getenforce"])

    # ── IRQ balance ───────────────────────────────────────────────────────────

    def get_irqbalance_status(self) -> str:
        out = self._run(["systemctl", "is-active", "irqbalance"])
        return out if out else "N/A"

    # ── RAPL TDP (CWF via TPMI / MSR) ────────────────────────────────────────

    def get_tdp_pl1_watts(self) -> str:
        """Read PL1 from MSR 0x610 or TPMI debugfs."""
        # Try TPMI debugfs first (DMR, CWF)
        import glob
        import os
        tpmi_paths = sorted(glob.glob("/sys/kernel/debug/tpmi-*/tpmi-id-00"))
        if tpmi_paths:
            try:
                with open(os.path.join(tpmi_paths[0], "mem_dump"), "rb") as f:
                    data = f.read(80)
                val = int.from_bytes(data[0x48:0x4c], "little")
                pl1_raw = val & 0x3FFFF
                return f"{pl1_raw / 8:.1f}"   # 1/8 W per LSB
            except Exception:
                pass
        # Fall back to MSR 0x610
        try:
            r = subprocess.run(["rdmsr", "-p", "0", "0x610"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                v = int(r.stdout.strip(), 16)
                pl1_raw = v & 0x7FFF
                unit_r = subprocess.run(["rdmsr", "-p", "0", "0x606"],
                                        capture_output=True, text=True, timeout=5)
                unit_exp = 0
                if unit_r.returncode == 0:
                    unit_exp = (int(unit_r.stdout.strip(), 16) >> 8) & 0x1F
                return f"{pl1_raw / (2 ** unit_exp):.1f}"
        except Exception:
            pass
        return "N/A"

    # ── hostname / QDF ────────────────────────────────────────────────────────

    def get_hostname(self) -> str:
        return self._run(["hostname", "-s"])

    def get_qdf(self) -> str:
        """Read QDF from DMI / BIOS chassis or return N/A."""
        out = self._run(["sudo", "dmidecode", "-t", "chassis"])
        for line in out.splitlines():
            if "Version:" in line:
                return line.split(":", 1)[1].strip()
        return "N/A"

    def get_cmdline(self) -> str:
        try:
            with open("/proc/cmdline") as f:
                return f.read().strip()
        except Exception:
            return "N/A"
