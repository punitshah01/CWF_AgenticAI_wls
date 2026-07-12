"""
AgentSysPerf — unified Agentic AI CPU-tier performance analytics.

Shared, dependency-free analytics layer used by all 5 benchmark runners
(WebArena, AppWorld, OSWorld, SWE-bench, T-Bench) to emit a normalized
KPI contract: agent-loop latency percentiles, SLA pass/fail, cost per
completed task, active agents per vCPU, queue-depth/token-turnover
metrics, phase-level timing, and concurrency-sweep capacity detection.

See docs/agentsysperf.md for the full architecture, KPI formulas, and
usage guide.
"""

from common.agentsysperf.models import (
    CostModelConfig,
    CostModelResult,
    PhaseAttribution,
    PhaseTiming,
    RunRecord,
    SLOConfig,
    SLOResult,
    TaskRecord,
)
from common.agentsysperf.summary import build_run_summary, write_run_artifacts

__all__ = [
    "CostModelConfig",
    "CostModelResult",
    "PhaseAttribution",
    "PhaseTiming",
    "RunRecord",
    "SLOConfig",
    "SLOResult",
    "TaskRecord",
    "build_run_summary",
    "write_run_artifacts",
]
