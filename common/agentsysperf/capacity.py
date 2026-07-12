#!/usr/bin/env python3
"""
AgentSysPerf — capacity / saturation detector for concurrency sweeps.

Given a series of (concurrency, throughput, p95_latency, slo_passed) points
collected by the sweep engine, determine:

  * saturation_point   — first concurrency level where the SLA fails, or
                          where marginal throughput gain collapses
                          (< ``marginal_gain_floor`` fraction of the best
                          per-step gain observed so far).
  * recommended_point   — highest concurrency that still passes SLA and has
                          "stable" tail latency (p99/p95 ratio below
                          ``tail_ratio_max``).

Known limitation: the marginal-gain-collapse rule compares a single step's
gain to the best gain seen so far, so a transient measurement dip (noise)
could in principle trigger an early false-positive saturation call. Callers
that need extra robustness should increase ``repetitions`` in
``run_concurrency_sweep`` (the sweep engine averages throughput across
repetitions per concurrency point before this detector ever runs) rather
than smoothing inside this deterministic, single-pass detector.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SweepPoint:
    concurrency: int
    throughput_tasks_per_hour: float
    p95_latency_ms: Optional[float]
    p99_latency_ms: Optional[float]
    slo_passed: bool


@dataclass
class CapacitySummary:
    saturation_point: Optional[int]
    saturation_reason: Optional[str]
    recommended_operating_point: Optional[int]
    recommended_reason: Optional[str]
    points: List[SweepPoint]


def detect_capacity(
    points: List[SweepPoint],
    marginal_gain_floor: float = 0.10,
    tail_ratio_max: float = 1.5,
) -> CapacitySummary:
    """Detect the saturation point and recommended operating point.

    ``points`` must be sorted ascending by concurrency.
    """
    if not points:
        return CapacitySummary(
            saturation_point=None,
            saturation_reason="no sweep points supplied",
            recommended_operating_point=None,
            recommended_reason="no sweep points supplied",
            points=[],
        )

    ordered = sorted(points, key=lambda p: p.concurrency)

    saturation_point: Optional[int] = None
    saturation_reason: Optional[str] = None

    best_step_gain = 0.0
    prev_throughput = ordered[0].throughput_tasks_per_hour

    for point in ordered:
        if not point.slo_passed:
            saturation_point = point.concurrency
            saturation_reason = "first concurrency level where SLA failed"
            break

        gain = point.throughput_tasks_per_hour - prev_throughput
        if gain > best_step_gain:
            best_step_gain = gain
        elif best_step_gain > 0 and gain < best_step_gain * marginal_gain_floor:
            saturation_point = point.concurrency
            saturation_reason = (
                f"marginal throughput gain ({gain:.2f}) collapsed below "
                f"{marginal_gain_floor:.0%} of best observed step gain "
                f"({best_step_gain:.2f})"
            )
            break
        prev_throughput = point.throughput_tasks_per_hour

    # Recommended point: highest concurrency that (a) passes SLA and
    # (b) is at or before the saturation point and (c) has a stable
    # p99/p95 tail-latency ratio.
    recommended_point: Optional[int] = None
    recommended_reason: Optional[str] = None

    candidates = [
        p
        for p in ordered
        if p.slo_passed and (saturation_point is None or p.concurrency < saturation_point)
    ]
    for point in reversed(candidates):
        if point.p95_latency_ms is not None and point.p99_latency_ms is not None:
            ratio = point.p99_latency_ms / point.p95_latency_ms if point.p95_latency_ms != 0 else None
        else:
            ratio = None
        if ratio is None or ratio <= tail_ratio_max:
            recommended_point = point.concurrency
            recommended_reason = (
                "highest SLA-passing concurrency with stable tail latency "
                f"(p99/p95={ratio:.2f})" if ratio is not None
                else "highest SLA-passing concurrency (tail-latency ratio unavailable)"
            )
            break

    if recommended_point is None and candidates:
        # Fall back to the highest SLA-passing point even if tail latency
        # looked unstable at every candidate — still better than nothing,
        # but the reason makes that explicit.
        point = candidates[-1]
        recommended_point = point.concurrency
        recommended_reason = (
            "highest SLA-passing concurrency; no candidate met the tail-latency "
            "stability bar so this is a best-effort pick"
        )

    return CapacitySummary(
        saturation_point=saturation_point,
        saturation_reason=saturation_reason,
        recommended_operating_point=recommended_point,
        recommended_reason=recommended_reason,
        points=ordered,
    )
