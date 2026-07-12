#!/usr/bin/env python3
"""
AgentSysPerf — queue-depth and token-turnover calculators.
"""

from typing import Optional, Sequence

from common.agentsysperf.percentiles import mean, p95


def queue_depth_stats(samples: Sequence[float]) -> dict:
    """Return {mean, p95} queue-depth stats. Empty input -> both None."""
    return {
        "queue_depth_mean": mean(samples),
        "queue_depth_p95": p95(samples),
    }


def token_turnover_per_s(total_tokens: int, runtime_s: float) -> Optional[float]:
    """Tokens processed (in + out) per second of wall-clock runtime."""
    if runtime_s <= 0:
        return None
    return round(total_tokens / runtime_s, 4)


def tasks_completed_per_hour(tasks_completed: int, runtime_s: float) -> Optional[float]:
    if runtime_s <= 0:
        return None
    return round(tasks_completed / (runtime_s / 3600.0), 4)


def active_agents_per_vcpu(active_agents: int, vcpus: int) -> Optional[float]:
    """Concurrency density metric used for SKU/platform sizing decisions."""
    if vcpus <= 0:
        return None
    return round(active_agents / vcpus, 6)
