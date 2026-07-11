#!/usr/bin/env python3
"""
AgentSysPerf — unified run summary builder + artifact writers.

This is the single integration point every benchmark runner calls to emit
the normalized AgentSysPerf KPI contract (section B of the spec) alongside
its existing, unchanged legacy outputs.

Usage (from a runner)::

    from common.agentsysperf.summary import build_run_summary, write_run_artifacts

    summary = build_run_summary(
        workload="tbench",
        run_id=run_id,
        active_agents=1,
        vcpus=cpu.get_total_cores(),
        runtime_s=runtime_s,
        tasks_total=tasks_total,
        tasks_completed=tasks_passed,
        loop_latencies_ms=[...],          # or [] if unavailable
        tokens_total=0,                    # best effort
        queue_depth_samples=[],
        cost_cfg=CostModelConfig(...),
        slo_cfg=SLOConfig(...),
    )
    write_run_artifacts(out_dir, summary)
"""

import csv
import json
from pathlib import Path
from typing import Dict, Optional, Sequence

from common.agentsysperf.cost import compute_cost
from common.agentsysperf.models import CostModelConfig, PhaseTiming, SLOConfig
from common.agentsysperf.percentiles import mean, p50, p95, p99
from common.agentsysperf.phases import (
    aggregate_phases,
    infer_phase_shares_from_mean_latency,
)
from common.agentsysperf.queue_stats import (
    active_agents_per_vcpu,
    queue_depth_stats,
    tasks_completed_per_hour,
    token_turnover_per_s,
)
from common.agentsysperf.sla import evaluate_slo


def build_run_summary(
    workload: str,
    run_id: str,
    active_agents: int,
    vcpus: int,
    runtime_s: float,
    tasks_total: int,
    tasks_completed: int,
    loop_latencies_ms: Optional[Sequence[float]] = None,
    tokens_total: int = 0,
    queue_depth_samples: Optional[Sequence[float]] = None,
    phase_samples: Optional[Sequence[PhaseTiming]] = None,
    cost_cfg: Optional[CostModelConfig] = None,
    slo_cfg: Optional[SLOConfig] = None,
    latency_approximation: Optional[str] = None,
) -> Dict:
    """Compute the full normalized AgentSysPerf KPI + phase + SLO + cost bundle.

    ``latency_approximation``: when ``loop_latencies_ms`` is not a true
    per-task distribution (e.g. derived from a single total-runtime number
    for a coarse-grained workload), pass a short label describing the
    approximation (e.g. "single_sample_total_runtime"). Left ``None`` when
    percentiles are computed from true per-task records.
    """
    loop_latencies_ms = list(loop_latencies_ms or [])
    queue_depth_samples = list(queue_depth_samples or [])
    phase_samples = list(phase_samples or [])

    success_rate = (tasks_completed / tasks_total) if tasks_total > 0 else None

    lat_p50, lat_p95, lat_p99 = (
        p50(loop_latencies_ms),
        p95(loop_latencies_ms),
        p99(loop_latencies_ms),
    )

    cost_result = None
    if cost_cfg is not None:
        cost_result = compute_cost(cost_cfg, tasks_completed)

    slo_result = None
    if slo_cfg is not None:
        slo_result = evaluate_slo(
            slo_cfg,
            p95_latency_ms=lat_p95,
            success_rate=success_rate,
            cost_per_completed_task_usd=(
                cost_result.cost_per_completed_task_usd if cost_result else None
            ),
        )

    # Phase timing: use true measurements if present, otherwise fall back to
    # an explicitly labeled "inferred" split of the mean loop latency.
    mean_latency = mean(loop_latencies_ms)
    inferred_shares = infer_phase_shares_from_mean_latency(mean_latency)
    phase_attrs = aggregate_phases(phase_samples, inferred_from_total=inferred_shares)

    kpi = {
        "workload": workload,
        "run_id": run_id,
        "active_agents": active_agents,
        "vcpus": vcpus,
        "active_agents_per_vcpu": active_agents_per_vcpu(active_agents, vcpus),
        "loop_latency_p50_ms": lat_p50,
        "loop_latency_p95_ms": lat_p95,
        "loop_latency_p99_ms": lat_p99,
        "loop_latency_approximation": latency_approximation,
        "cost_per_completed_task_usd": (
            cost_result.cost_per_completed_task_usd if cost_result else None
        ),
        "queue_depth_mean": queue_depth_stats(queue_depth_samples)["queue_depth_mean"],
        "queue_depth_p95": queue_depth_stats(queue_depth_samples)["queue_depth_p95"],
        "token_turnover_per_s": token_turnover_per_s(tokens_total, runtime_s),
        "tasks_completed_per_hour": tasks_completed_per_hour(tasks_completed, runtime_s),
        "tasks_total": tasks_total,
        "tasks_completed": tasks_completed,
        "success_rate": success_rate,
        "runtime_s": runtime_s,
    }

    if slo_result is not None:
        kpi.update(slo_result.as_dict())
    else:
        kpi.update({"slo_passed": None, "slo_status": "not_evaluated", "slo_failure_reason": None})

    return {
        "kpi": kpi,
        "phases": [p.as_dict() for p in phase_attrs],
        "cost": cost_result.as_dict() if cost_result else None,
        "slo": slo_result.as_dict() if slo_result else None,
    }


def write_run_artifacts(output_dir: Path, summary: Dict) -> Dict[str, Path]:
    """Write agentsysperf_summary.json/.csv, phase_metrics.csv and
    slo_evaluation.json into ``output_dir``. Additive only — never touches
    any pre-existing legacy files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}

    summary_json = output_dir / "agentsysperf_summary.json"
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    written["summary_json"] = summary_json

    summary_csv = output_dir / "agentsysperf_summary.csv"
    kpi = summary["kpi"]
    with open(summary_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(list(kpi.keys()))
        writer.writerow([kpi[k] for k in kpi.keys()])
    written["summary_csv"] = summary_csv

    phase_csv = output_dir / "phase_metrics.csv"
    with open(phase_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["phase", "mean_ms", "p95_ms", "source", "reason"])
        for p in summary["phases"]:
            writer.writerow([p["phase"], p["mean_ms"], p["p95_ms"], p["source"], p["reason"]])
    written["phase_csv"] = phase_csv

    slo_json = output_dir / "slo_evaluation.json"
    with open(slo_json, "w") as f:
        json.dump(summary["slo"] or {"slo_passed": None, "note": "SLO not configured"}, f, indent=2)
    written["slo_json"] = slo_json

    return written
