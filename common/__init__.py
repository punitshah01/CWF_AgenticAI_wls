"""
CWF Agentic AI — Common Utilities
===================================
Shared Python utilities for all agentic benchmark runners.

Modelled after pnpwls/common/ — provides the same module contracts so
scripts can be reused across pnpwls and this repo with minimal changes.

Modules:
    cpu_info        — CPUInfo: lscpu topology (cores, NUMA, threads_per_core)
    os_info         — OSInfo: BIOS, microcode, kernel, THP, governor
    system_info     — Backward-compat wrapper: get_system_info() -> (CPUInfo, OSInfo)
    system_metadata — get_system_metadata(): full snapshot OrderedDict
    platform_info   — detect_platform(): CWF / DMR / GNR / SRF / EMR / SPR …
    csv_writer      — write_csv_row(): intelligent CSV append
    json_results    — ResultsJsonWriter: structured JSON output
    telemetry/      — EMON, RAPL, SSMON, PTAT collectors + TelemetryManager
"""

from .system_info import CPUInfo, OSInfo, get_system_info  # noqa: F401
from .platform_info import detect_platform, get_platform_info  # noqa: F401
from .csv_writer import write_csv_row  # noqa: F401

_DOCKER_LAZY = {
    "DockerUtils":          "docker_utils",
    "DockerConfig":         "docker_utils",
    "create_docker_manager": "docker_utils",
}


def __getattr__(name: str):
    if name in _DOCKER_LAZY:
        from . import docker_utils  # noqa: PLC0415
        return getattr(docker_utils, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CPUInfo", "OSInfo", "get_system_info",
    "detect_platform", "get_platform_info",
    "write_csv_row",
]
