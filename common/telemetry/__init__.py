"""
Telemetry Collection Package
Provides Intel telemetry collection and processing for EMON, RAPL, SSMON, PTAT.

Mirrors pnpwls/common/telemetry/__init__.py API contract exactly.

Main Interface:
    TelemetryManager  — High-level facade for all workload runners (RECOMMENDED)
    TemperatureMonitor — Platform-aware temperature monitoring facade

Individual Collectors:
    EmonCollector  — EMON collection + EDP post-processing (emon -collect-edp)
    RaplCollector  — RAPL power domain polling
    PTATCollector  — Temperature (legacy platforms)
    SSMONCollector — Temperature (CWF / DMR / GNR)

Constants (mirror pnpwls):
    DEFAULT_BEGIN_SAMPLE, DEFAULT_DIRTY_SAMPLES
    LOW_COPY_BEGIN_SAMPLE, LOW_COPY_DIRTY_SAMPLES
    SPEED_BEGIN_SAMPLE, SPEED_DIRTY_SAMPLES
    LOW_COPY_THRESHOLD

Utility Functions (mirror pnpwls):
    resolve_emon_views     — Translate argparse flags → view dict
    read_emon_socket_view  — Parse __mpp_socket_view_summary.csv → (header, values)
    read_emon_core_view    — Parse __mpp_core_view_summary.csv → (header, values)
    read_emon_system_view  — Parse __mpp_system_view_summary.csv → (header, values)
    get_emon_csv_header    — Extract CSV header string from EMON CSV
"""

# Main interface (recommended for workload runners)
from .manager import TelemetryManager          # noqa: F401
from .temperature import TemperatureMonitor    # noqa: F401

# Individual collectors
from .emon  import EmonCollector               # noqa: F401
from .rapl  import RaplCollector               # noqa: F401
from .ssmon import SSMONCollector              # noqa: F401
from .ptat  import PTATCollector               # noqa: F401

# Constants (same names as pnpwls so runners can use either repo unchanged)
from .emon import (                            # noqa: F401
    TelemetryStatus,
    DEFAULT_BEGIN_SAMPLE,
    DEFAULT_DIRTY_SAMPLES,
    SEP_DIR_DEFAULT,
)

# CSV reader utilities (same API as pnpwls)
from .emon import (                            # noqa: F401
    _read_emon_csv as _read_emon_csv,
    read_emon_socket_view,
    read_emon_core_view,
    read_emon_system_view,
    get_emon_csv_header,
)

# pnpwls compatibility stubs for constants not used in CWF but referenced
# by code that shares runners with pnpwls
LOW_COPY_BEGIN_SAMPLE  = 50
LOW_COPY_DIRTY_SAMPLES = 50
SPEED_BEGIN_SAMPLE     = 50
SPEED_DIRTY_SAMPLES    = 50
LOW_COPY_THRESHOLD     = 32


def resolve_emon_views(args, uses_limited_cores: bool = False) -> dict:
    """Translate argparse flags into a consistent EMON view dict.

    Mirrors pnpwls/common/telemetry/__init__.py:resolve_emon_views() exactly.

    Rules:
        1. socket view is always enabled
        2. core view auto-enabled when using limited (< all) cores
        3. uncore / detailed view only when explicitly requested

    Args:
        args: argparse.Namespace — expects core_view, uncore_view, detailed_view attrs.
        uses_limited_cores: True when fewer than all physical cores are used.

    Returns:
        dict: socket_view, core_view, uncore_view, detailed_view, views_str
    """
    socket_view   = True
    core_view     = getattr(args, 'core_view',     False) or uses_limited_cores
    uncore_view   = getattr(args, 'uncore_view',   False)
    detailed_view = getattr(args, 'detailed_view', False)

    parts = ['socket']
    if uncore_view:
        parts.extend(['system', 'uncore'])
    if core_view:
        parts.append('core')
    views_str = ','.join(parts)

    return {
        'socket_view':   socket_view,
        'core_view':     core_view,
        'uncore_view':   uncore_view,
        'detailed_view': detailed_view,
        'views_str':     views_str,
    }


def get_metric_from_summary(csv_path, metric_name: str) -> float:
    """Extract a single metric value from an EMON summary CSV.

    Mirrors pnpwls get_metric_from_summary() for cross-repo compatibility.

    Args:
        csv_path: Path to __mpp_*_summary.csv
        metric_name: Exact metric name (e.g. 'metric_CPU operating frequency (GHz)')

    Returns:
        float value or 0.0 if not found / parse error.
    """
    try:
        from pathlib import Path
        with open(Path(csv_path)) as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 2 and parts[0].strip() == metric_name:
                    return float(parts[1].strip())
    except Exception:
        pass
    return 0.0


__all__ = [
    # Main interfaces
    "TelemetryManager",
    "TemperatureMonitor",

    # Individual collectors
    "EmonCollector",
    "RaplCollector",
    "SSMONCollector",
    "PTATCollector",

    # Status enum
    "TelemetryStatus",

    # Constants
    "DEFAULT_BEGIN_SAMPLE",
    "DEFAULT_DIRTY_SAMPLES",
    "LOW_COPY_BEGIN_SAMPLE",
    "LOW_COPY_DIRTY_SAMPLES",
    "SPEED_BEGIN_SAMPLE",
    "SPEED_DIRTY_SAMPLES",
    "LOW_COPY_THRESHOLD",
    "SEP_DIR_DEFAULT",

    # View utilities
    "resolve_emon_views",
    "read_emon_socket_view",
    "read_emon_core_view",
    "read_emon_system_view",
    "get_emon_csv_header",
    "get_metric_from_summary",
]
