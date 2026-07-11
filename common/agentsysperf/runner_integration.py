#!/usr/bin/env python3
"""
AgentSysPerf — runner integration helper.

Thin, defensive glue used by all 5 benchmark run.py entry points to emit
the normalized AgentSysPerf KPI/SLA/cost/phase artifacts alongside their
existing (unchanged) legacy results.csv / results.json outputs.

Never raises: any failure while computing/writing AgentSysPerf artifacts is
caught and logged as a warning so a bug in this optional layer can never
break the primary benchmark result pipeline (section G — non-breaking
guarantee).
"""

import argparse
from pathlib import Path
from typing import Dict, Optional

from common.agentsysperf.models import CostModelConfig, SLOConfig
from common.agentsysperf.summary import build_run_summary, write_run_artifacts


def add_agentsysperf_args(parser: argparse.ArgumentParser) -> None:
    """Register the shared, opt-in AgentSysPerf CLI flags on a runner parser.

    All flags default to values that keep the cost model usable out of the
    box while leaving SLA enforcement disabled (no threshold => not
    evaluated) so existing automation is unaffected.
    """
    group = parser.add_argument_group("AgentSysPerf")
    group.add_argument(
        "--node-hourly-usd", type=float, default=5.0,
        help="Assumed on-demand node cost ($/hour) for cost-per-completed-task.",
    )
    group.add_argument(
        "--energy-price-usd-per-kwh", type=float, default=None,
        help="Energy price ($/kWh). If unset, cost model falls back to compute-only.",
    )
    group.add_argument(
        "--sla-p95-ms", type=float, default=None,
        help="SLA: max acceptable p95 agent-loop latency (ms). Unset = not enforced.",
    )
    group.add_argument(
        "--sla-min-success-rate", type=float, default=None,
        help="SLA: min acceptable task success rate (0-1). Unset = not enforced.",
    )
    group.add_argument(
        "--sla-max-cost-per-task-usd", type=float, default=None,
        help="SLA: max acceptable cost per completed task ($). Unset = not enforced.",
    )
    group.add_argument(
        "--active-agents", type=int, default=1,
        help="Number of concurrent agent instances in this run (for active_agents_per_vcpu).",
    )


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def emit_agentsysperf_artifacts(
    output_dir: Path,
    workload: str,
    run_id: str,
    vcpus: int,
    bench_results: Dict,
    tm,
    args: argparse.Namespace,
    tasks_total_key: str = "tasks_total",
    tasks_completed_key: str = "tasks_passed",
    runtime_key: str = "total_runtime_s",
    active_agents: Optional[int] = None,
    loop_latencies_ms: Optional[list] = None,
    tokens_total: Optional[int] = None,
    latency_approximation: Optional[str] = None,
) -> Optional[Dict[str, Path]]:
    """Compute + write the normalized AgentSysPerf artifacts for one run.

    ``bench_results`` is the workload-specific results dict already produced
    by the runner (string-valued, as today). ``tm`` is the run's
    TelemetryManager instance (used for measured package/DRAM power when
    available). Returns the dict of written artifact paths, or ``None`` if
    artifact generation failed (already logged) so callers can safely ignore
    the return value.
    """
    try:
        tasks_total = _to_int(bench_results.get(tasks_total_key), 0)
        tasks_completed = _to_int(bench_results.get(tasks_completed_key), 0)
        runtime_s = _to_float(bench_results.get(runtime_key), 0.0)
        agents = active_agents if active_agents is not None else getattr(args, "active_agents", 1)

        # Best-effort loop-latency approximation: most runners only expose a
        # single total-runtime number today (no true per-task timing), so we
        # approximate the per-task loop latency as runtime / completed tasks,
        # replicated so percentile math is well-defined, and explicitly tag
        # the approximation rather than presenting it as a true distribution.
        # Callers with true per-task timing (e.g. WebArena) pass
        # loop_latencies_ms / latency_approximation=None directly, which
        # takes precedence over this fallback.
        approximation = latency_approximation
        latencies = loop_latencies_ms
        if latencies is None:
            latencies = []
            if runtime_s > 0 and tasks_completed > 0:
                avg_latency_ms = (runtime_s * 1000.0) / tasks_completed
                latencies = [avg_latency_ms] * tasks_completed
                approximation = "uniform_avg_from_total_runtime"
            elif runtime_s > 0:
                latencies = [runtime_s * 1000.0]
                approximation = "single_sample_total_runtime"

        pkg_power = getattr(tm, "pkg_power_w", None)
        dram_power = getattr(tm, "dram_power_w", None)
        cost_cfg = CostModelConfig(
            node_hourly_usd=getattr(args, "node_hourly_usd", 5.0),
            runtime_s=runtime_s,
            avg_package_power_w=pkg_power if isinstance(pkg_power, (int, float)) else None,
            avg_dram_power_w=dram_power if isinstance(dram_power, (int, float)) else None,
            energy_price_usd_per_kwh=getattr(args, "energy_price_usd_per_kwh", None),
        )

        slo_cfg = None
        sla_p95 = getattr(args, "sla_p95_ms", None)
        sla_success = getattr(args, "sla_min_success_rate", None)
        sla_cost = getattr(args, "sla_max_cost_per_task_usd", None)
        if any(v is not None for v in (sla_p95, sla_success, sla_cost)):
            slo_cfg = SLOConfig(
                p95_latency_ms_max=sla_p95,
                min_success_rate=sla_success,
                max_cost_per_task_usd=sla_cost,
            )

        summary = build_run_summary(
            workload=workload,
            run_id=run_id,
            active_agents=agents,
            vcpus=vcpus,
            runtime_s=runtime_s,
            tasks_total=tasks_total,
            tasks_completed=tasks_completed,
            loop_latencies_ms=latencies,
            tokens_total=tokens_total or 0,
            cost_cfg=cost_cfg,
            slo_cfg=slo_cfg,
            latency_approximation=approximation,
        )
        return write_run_artifacts(output_dir, summary)
    except Exception as exc:  # noqa: BLE001 — never break the primary pipeline
        print(f"[agentsysperf] WARNING: failed to emit AgentSysPerf artifacts: {exc}")
        return None
