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
    cli_utils       — get_base_parser(), parse_config(), setup_logging()
    docker_utils    — pull_image(), run_container(), container_exists()
    git_provenance  — get_git_sha(), get_repo_url(), get_provenance_dict()
    run_generic     — run_cmd(), stream_output()
    tuneup_utils    — set_cpu_governor(), disable_aslr(), restore_defaults()
    metadata        — build_metadata()
    telemetry/      — EMON, RAPL, SSMON, PTAT collectors + TelemetryManager
"""

from .system_info import CPUInfo, OSInfo, get_system_info  # noqa: F401
from .platform_info import detect_platform, get_platform_info  # noqa: F401
from .csv_writer import write_csv_row  # noqa: F401
from . import cli_utils  # noqa: F401
from . import docker_utils  # noqa: F401
from . import git_provenance  # noqa: F401
from . import run_generic  # noqa: F401
from . import tuneup_utils  # noqa: F401
from . import metadata  # noqa: F401

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
