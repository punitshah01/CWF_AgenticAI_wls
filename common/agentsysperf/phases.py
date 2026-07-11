#!/usr/bin/env python3
"""
AgentSysPerf — phase timing aggregator.

Aggregates per-task :class:`PhaseTiming` samples into per-phase
mean/p95 with an explicit attribution source (measured / inferred /
unavailable), so downstream consumers never have to guess why a field
is null.
"""

from typing import List, Optional, Sequence

from common.agentsysperf.models import PHASE_NAMES, PhaseAttribution, PhaseTiming
from common.agentsysperf.percentiles import mean, p95


def aggregate_phases(
    phase_samples: Sequence[PhaseTiming],
    inferred_from_total: Optional[dict] = None,
) -> List[PhaseAttribution]:
    """Aggregate a list of per-task :class:`PhaseTiming` into per-phase stats.

    ``inferred_from_total``: optional ``{phase: fraction}`` map used to
    derive a best-effort estimate (source="inferred") for phases that have
    no direct measurements anywhere in ``phase_samples``, by splitting the
    mean end-to-end loop latency according to fixed fractions. Workloads
    with only coarse task-level timing use this to still emit a non-null
    (but clearly labeled) phase breakdown.
    """
    results: List[PhaseAttribution] = []

    for phase in PHASE_NAMES:
        field = f"{phase}_ms"
        measured = [
            getattr(p, field) for p in phase_samples if getattr(p, field) is not None
        ]
        if measured:
            results.append(
                PhaseAttribution(
                    phase=phase,
                    mean_ms=mean(measured),
                    p95_ms=p95(measured),
                    source="measured",
                )
            )
        elif inferred_from_total and phase in inferred_from_total:
            results.append(
                PhaseAttribution(
                    phase=phase,
                    mean_ms=inferred_from_total[phase],
                    p95_ms=None,
                    source="inferred",
                    reason="derived from total loop latency using fixed phase-share heuristic",
                )
            )
        else:
            results.append(
                PhaseAttribution(
                    phase=phase,
                    mean_ms=None,
                    p95_ms=None,
                    source="unavailable",
                    reason="no per-phase telemetry instrumented for this workload/run",
                )
            )

    return results


# Default phase-share heuristic used to derive "inferred" phase timings from
# a single end-to-end loop-latency number when no per-phase telemetry exists.
# Values are fractions of total loop latency and must sum to 1.0.
DEFAULT_PHASE_SHARE = {
    "admit": 0.05,
    "retrieve": 0.15,
    "act": 0.45,
    "decision": 0.25,
    "commit": 0.10,
}


def infer_phase_shares_from_mean_latency(
    mean_loop_latency_ms: Optional[float],
    shares: Optional[dict] = None,
) -> Optional[dict]:
    """Split a mean loop latency into an inferred per-phase breakdown."""
    if mean_loop_latency_ms is None:
        return None
    shares = shares or DEFAULT_PHASE_SHARE
    return {phase: mean_loop_latency_ms * frac for phase, frac in shares.items()}
