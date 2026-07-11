#!/usr/bin/env python3
"""
AgentSysPerf — SLA (Service Level Agreement) evaluator.

Evaluates a run's normalized KPIs against configurable thresholds:
  * p95 loop latency ceiling
  * minimum success/completion rate
  * optional maximum cost-per-completed-task

Produces a pass/fail tag plus explicit, machine-readable failure reasons.
"""

from typing import List, Optional

from common.agentsysperf.models import SLOConfig, SLOResult


def evaluate_slo(
    slo: SLOConfig,
    p95_latency_ms: Optional[float],
    success_rate: Optional[float],
    cost_per_completed_task_usd: Optional[float] = None,
) -> SLOResult:
    """Evaluate one run against an :class:`SLOConfig`.

    Any threshold left as ``None`` in ``slo`` is not evaluated. Any input
    metric that is ``None`` (missing data) is treated as "unable to verify"
    and reported as a failure reason rather than silently passing, unless
    the corresponding threshold is also unset.
    """
    reasons: List[str] = []

    if slo.p95_latency_ms_max is not None:
        if p95_latency_ms is None:
            reasons.append("p95_loop_latency_unavailable")
        elif p95_latency_ms > slo.p95_latency_ms_max:
            reasons.append(
                f"p95_loop_latency_ms={p95_latency_ms:.1f} "
                f"exceeds threshold={slo.p95_latency_ms_max:.1f}"
            )

    if slo.min_success_rate is not None:
        if success_rate is None:
            reasons.append("success_rate_unavailable")
        elif success_rate < slo.min_success_rate:
            reasons.append(
                f"success_rate={success_rate:.4f} "
                f"below threshold={slo.min_success_rate:.4f}"
            )

    if slo.max_cost_per_task_usd is not None:
        if cost_per_completed_task_usd is None:
            reasons.append("cost_per_completed_task_unavailable")
        elif cost_per_completed_task_usd > slo.max_cost_per_task_usd:
            reasons.append(
                f"cost_per_completed_task_usd={cost_per_completed_task_usd:.4f} "
                f"exceeds threshold={slo.max_cost_per_task_usd:.4f}"
            )

    return SLOResult(passed=len(reasons) == 0, failure_reasons=reasons)
