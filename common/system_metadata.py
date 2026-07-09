#!/usr/bin/env python3
"""
System Metadata Module
Consolidated system snapshot used by all benchmark runners.

Usage:
    from common.system_metadata import get_system_metadata

    ctx.cpu_info = CPUInfo()
    ctx.os_info  = OSInfo()
    ctx.sys_meta = get_system_metadata(ctx.cpu_info, ctx.os_info)

    # In CSV row builder:
    common_data.update(ctx.sys_meta)
"""

import subprocess
import urllib.error
import urllib.request
import json as _json
from collections import OrderedDict

from .cpu_info import CPUInfo
from .os_info import OSInfo
from .platform_info import detect_platform


def _read_msr(addr: str) -> str:
    """Read MSR via rdmsr; load msr module first if needed."""
    try:
        subprocess.run(["modprobe", "msr"], capture_output=True, timeout=3)
        r = subprocess.run(["rdmsr", "-p", "0", addr],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            v = r.stdout.strip()
            return ("0x" + v) if not v.lower().startswith("0x") else v
    except Exception:
        pass
    return "N/A"


def get_system_metadata(cpu: CPUInfo, os_info: OSInfo,
                        run_id: str = "",
                        experiment_name: str = "") -> OrderedDict:
    """
    Build and return a full system-metadata OrderedDict.

    Fields match the standard pnpwls CSV layout for cross-run comparability.
    Agentic-specific fields (experiment_name) are appended at the end.
    """
    meta: OrderedDict = OrderedDict()

    # ── Identity ──────────────────────────────────────────────────────────────
    meta["run_id"]           = run_id
    meta["hostname"]         = os_info.get_hostname()
    meta["experiment_name"]  = experiment_name

    # ── Platform ──────────────────────────────────────────────────────────────
    meta["platform"]         = detect_platform()
    meta["cpu_model"]        = cpu.get_model_name()
    meta["cpu_family"]       = str(cpu.get_cpu_family())
    meta["cpu_model_num"]    = str(cpu.get_cpu_model())
    meta["cpu_stepping"]     = str(cpu.get_cpu_stepping())

    # ── Topology ─────────────────────────────────────────────────────────────
    meta["cpu_sockets"]         = str(cpu.get_sockets())
    meta["cores_per_socket"]    = str(cpu.get_cores_per_socket())
    meta["threads_per_core"]    = str(cpu.get_threads_per_core())
    meta["total_cores"]         = str(cpu.get_total_cores())
    meta["numa_nodes"]          = str(cpu.get_numa_nodes())
    meta["numa_node_str"]       = "; ".join(
        f"N{k}={v}" for k, v in cpu.get_all_numa_cpus().items()
    )
    meta["cpu_max_mhz"]         = cpu.get_cpu_max_mhz()

    # ── OS ───────────────────────────────────────────────────────────────────
    meta["os_release"]          = os_info.get_os_pretty_name()
    meta["kernel"]              = os_info.get_kernel()

    # ── Firmware ─────────────────────────────────────────────────────────────
    meta["bios_version"]        = os_info.get_bios_version()
    meta["microcode"]           = os_info.get_microcode()
    meta["qdf"]                 = os_info.get_qdf()

    # ── Memory ───────────────────────────────────────────────────────────────
    meta["memory_total_gb"]     = os_info.get_total_memory_gb()
    meta["memory_speed"]        = os_info.get_memory_speed()
    meta["dimm_config"]         = os_info.get_dimm_config()

    # ── Power / TDP ───────────────────────────────────────────────────────────
    meta["tdp_pl1_watts"]       = os_info.get_tdp_pl1_watts()

    # ── OS config ─────────────────────────────────────────────────────────────
    meta["cpu_governor"]        = os_info.get_cpu_governor()
    meta["thp_enabled"]         = os_info.get_thp_enabled()
    meta["thp_defrag"]          = os_info.get_thp_defrag()
    meta["numa_balancing"]      = os_info.get_numa_balancing()
    meta["nmi_watchdog"]        = os_info.get_nmi_watchdog()
    meta["cstates_enabled"]     = os_info.get_cstates_enabled()
    meta["selinux"]             = os_info.get_selinux()
    meta["irqbalance_status"]   = os_info.get_irqbalance_status()
    meta["cmdline"]             = os_info.get_cmdline()

    return meta


def get_ollama_metadata(port: int = 11434) -> OrderedDict:
    """Query Ollama for version, loaded model, and thread configuration.

    Gracefully returns "N/A" for each field if Ollama is unreachable or
    returns unexpected data — this is intentional so callers using an
    external/cloud LLM server don't crash.

    Args:
        port: Ollama API port (default 11434).

    Returns:
        OrderedDict with keys:
            ollama_version, ollama_model_name, ollama_model_size_gb,
            ollama_quantization, ollama_num_threads
    """
    meta: OrderedDict = OrderedDict()
    base = f"http://localhost:{port}"

    # ── Version ───────────────────────────────────────────────────────────────
    try:
        with urllib.request.urlopen(f"{base}/api/version", timeout=5) as r:
            data = _json.loads(r.read())
        meta["ollama_version"] = data.get("version", "N/A")
    except Exception:
        meta["ollama_version"] = "N/A"

    # ── Loaded model (from /api/ps) ───────────────────────────────────────────
    meta["ollama_model_name"]     = "N/A"
    meta["ollama_model_size_gb"]  = "N/A"
    meta["ollama_quantization"]   = "N/A"
    try:
        with urllib.request.urlopen(f"{base}/api/ps", timeout=5) as r:
            data = _json.loads(r.read())
        models = data.get("models") or []
        if models:
            m0 = models[0]
            meta["ollama_model_name"] = m0.get("name", "N/A")
            size_bytes = m0.get("size", 0) or 0
            meta["ollama_model_size_gb"] = (
                f"{size_bytes / 1e9:.1f}" if size_bytes > 0 else "N/A"
            )
            details = m0.get("details") or {}
            meta["ollama_quantization"] = details.get("quantization_level", "N/A")
    except Exception:
        pass

    # ── Thread config from systemd override ──────────────────────────────────
    meta["ollama_num_threads"] = "N/A"
    try:
        import re as _re
        override = "/etc/systemd/system/ollama.service.d/override.conf"
        with open(override) as f:
            for line in f:
                if "OLLAMA_NUM_THREADS" in line:
                    # e.g.  Environment="OLLAMA_NUM_THREADS=570"
                    # Extract the value after the last '=' and strip surrounding quotes
                    m = _re.search(r'OLLAMA_NUM_THREADS=(\d+)', line)
                    if m:
                        meta["ollama_num_threads"] = m.group(1)
                    break
    except Exception:
        pass

    return meta


__all__ = ["get_system_metadata", "get_ollama_metadata"]
