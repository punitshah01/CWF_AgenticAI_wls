#!/usr/bin/env python3
"""
AgentSysPerf — typed data models.

Normalized, workload-agnostic dataclasses used across the AgentSysPerf
analytics layer (percentiles, SLA, cost model, phase timing, capacity
sweeps). Kept dependency-free (stdlib only) so the module can be reused
from any of the 5 benchmark runners plus offline analysis scripts.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

# Phase names in the canonical Admit -> Retrieve -> Act -> Decision -> Commit
# agent-loop model shared by all 5 workloads.
PHASE_NAMES = ("admit", "retrieve", "act", "decision", "commit")

# Attribution source for a phase-level metric.
SOURCE_MEASURED = "measured"
SOURCE_INFERRED = "inferred"
SOURCE_UNAVAILABLE = "unavailable"


@dataclass
class PhaseTiming:
    """Per-phase latency (ms) for a single agent-loop iteration."""

    admit_ms: Optional[float] = None
    retrieve_ms: Optional[float] = None
    act_ms: Optional[float] = None
    decision_ms: Optional[float] = None
    commit_ms: Optional[float] = None

    def as_dict(self) -> Dict[str, Optional[float]]:
        return {f"{p}_ms": getattr(self, f"{p}_ms") for p in PHASE_NAMES}


@dataclass
class TaskRecord:
    """Normalized per-task record.

    ``loop_latency_ms`` is the end-to-end agent-loop latency for the task
    (or, for coarse-grained workloads, the best-effort approximation of it).
    """

    task_id: str
    success: bool
    loop_latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    phases: Optional[PhaseTiming] = None
    queue_depth_at_admit: Optional[float] = None


@dataclass
class PhaseAttribution:
    """Aggregated phase timing with an explicit data-source tag."""

    phase: str
    mean_ms: Optional[float]
    p95_ms: Optional[float]
    source: str  # measured | inferred | unavailable
    reason: Optional[str] = None

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SLOConfig:
    """SLA thresholds evaluated at run level."""

    p95_latency_ms_max: Optional[float] = None
    min_success_rate: Optional[float] = None
    max_cost_per_task_usd: Optional[float] = None


@dataclass
class SLOResult:
    """Outcome of evaluating a run against an :class:`SLOConfig`."""

    passed: bool
    failure_reasons: List[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "pass" if self.passed else "fail"

    def as_dict(self) -> Dict:
        return {
            "slo_passed": self.passed,
            "slo_status": self.status,
            "slo_failure_reason": "; ".join(self.failure_reasons) or None,
        }


@dataclass
class CostModelConfig:
    """Inputs for the cost-per-completed-task calculator."""

    node_hourly_usd: float
    runtime_s: float
    avg_package_power_w: Optional[float] = None
    avg_dram_power_w: Optional[float] = None
    energy_price_usd_per_kwh: Optional[float] = None


@dataclass
class CostModelResult:
    """Outputs of the cost model, including component breakdown."""

    total_run_cost_usd: float
    cost_per_completed_task_usd: Optional[float]
    compute_cost_component_usd: float
    energy_cost_component_usd: float
    total_cost_component_usd: float
    mode: str  # "compute_plus_energy" | "compute_only"
    assumption: Optional[str] = None

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RunRecord:
    """Normalized per-run record produced by every workload runner."""

    workload: str
    run_id: str
    active_agents: int
    vcpus: int
    tasks: List[TaskRecord] = field(default_factory=list)
    runtime_s: float = 0.0
    queue_depth_samples: List[float] = field(default_factory=list)
