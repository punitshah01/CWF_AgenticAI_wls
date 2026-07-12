#!/usr/bin/env python3
"""
AgentSysPerf — percentile utilities.

Deterministic, dependency-free percentile math used for loop-latency and
queue-depth distributions (p50 / p95 / p99).
"""

import math
from typing import List, Optional, Sequence


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile (0-100) using linear interpolation.

    Returns ``None`` for an empty input so callers can distinguish
    "no data" from a legitimate 0.0 value.
    """
    if not values:
        return None
    if not 0 <= pct <= 100:
        raise ValueError(f"pct must be in [0, 100], got {pct}")

    data = sorted(values)
    n = len(data)
    if n == 1:
        return float(data[0])

    # Linear interpolation between closest ranks (same convention as
    # numpy.percentile default "linear" method).
    rank = (pct / 100.0) * (n - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(data[int(rank)])
    frac = rank - lo
    return float(data[lo] + (data[hi] - data[lo]) * frac)


def p50(values: Sequence[float]) -> Optional[float]:
    return percentile(values, 50)


def p95(values: Sequence[float]) -> Optional[float]:
    return percentile(values, 95)


def p99(values: Sequence[float]) -> Optional[float]:
    return percentile(values, 99)


def mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return float(sum(values) / len(values))


def percentile_summary(values: Sequence[float]) -> dict:
    """Return the standard {p50, p95, p99, mean} bundle for a distribution."""
    return {
        "p50": p50(values),
        "p95": p95(values),
        "p99": p99(values),
        "mean": mean(values),
    }


def merge_distributions(distributions: List[Sequence[float]]) -> List[float]:
    """Flatten several per-run distributions into one sample list."""
    merged: List[float] = []
    for d in distributions:
        merged.extend(d)
    return merged
