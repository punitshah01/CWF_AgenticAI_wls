#!/usr/bin/env python3
"""
AgentSysPerf — concurrency sweep engine.

Reusable driver that runs a workload callable at a series of concurrency
("active agents") levels, evaluates SLA at each point, and detects the
saturation point / recommended operating point.

The sweep engine is decoupled from any particular benchmark: callers pass
a ``run_fn(concurrency: int) -> dict`` callable that executes one
measurement at a given concurrency and returns a dict with at least:
    {"throughput_tasks_per_hour": float,
     "loop_latencies_ms": [...],
     "slo_passed": bool}

This lets each of the 5 runners plug in their own execution strategy
(sequential batches, process pools, external harness invocation, ...)
without the sweep engine needing workload-specific knowledge.
"""

import csv
import json
import time
from pathlib import Path
from typing import Callable, Dict, List

from common.agentsysperf.capacity import SweepPoint, detect_capacity
from common.agentsysperf.percentiles import p95, p99


def run_concurrency_sweep(
    run_fn: Callable[[int], Dict],
    concurrency_points: List[int],
    repetitions: int = 1,
    warmup_s: float = 0.0,
    cooldown_s: float = 0.0,
) -> List[SweepPoint]:
    """Execute ``run_fn`` at each concurrency point (with repetitions) and
    return one aggregated :class:`SweepPoint` per concurrency level.
    """
    points: List[SweepPoint] = []

    for concurrency in concurrency_points:
        if warmup_s:
            time.sleep(warmup_s)

        throughputs: List[float] = []
        all_latencies: List[float] = []
        slo_pass_flags: List[bool] = []

        for _ in range(max(1, repetitions)):
            result = run_fn(concurrency)
            throughputs.append(result.get("throughput_tasks_per_hour", 0.0))
            all_latencies.extend(result.get("loop_latencies_ms", []))
            slo_pass_flags.append(bool(result.get("slo_passed", False)))

        if cooldown_s:
            time.sleep(cooldown_s)

        points.append(
            SweepPoint(
                concurrency=concurrency,
                # len(throughputs) == max(1, repetitions) (see loop above),
                # so this division is always safe (never zero).
                throughput_tasks_per_hour=(sum(throughputs) / len(throughputs)),
                p95_latency_ms=p95(all_latencies),
                p99_latency_ms=p99(all_latencies),
                slo_passed=all(slo_pass_flags),
            )
        )

    return points


def write_sweep_artifacts(output_dir: Path, points: List[SweepPoint]) -> Dict[str, Path]:
    """Write sweep_results.csv/.json, saturation_summary.json and
    recommended_operating_point.json.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}

    capacity = detect_capacity(points)

    results_csv = output_dir / "sweep_results.csv"
    with open(results_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["concurrency", "throughput_tasks_per_hour", "p95_latency_ms", "p99_latency_ms", "slo_passed"]
        )
        for p in capacity.points:
            writer.writerow(
                [p.concurrency, p.throughput_tasks_per_hour, p.p95_latency_ms, p.p99_latency_ms, p.slo_passed]
            )
    written["sweep_results_csv"] = results_csv

    results_json = output_dir / "sweep_results.json"
    with open(results_json, "w") as f:
        json.dump(
            [
                {
                    "concurrency": p.concurrency,
                    "throughput_tasks_per_hour": p.throughput_tasks_per_hour,
                    "p95_latency_ms": p.p95_latency_ms,
                    "p99_latency_ms": p.p99_latency_ms,
                    "slo_passed": p.slo_passed,
                }
                for p in capacity.points
            ],
            f,
            indent=2,
        )
    written["sweep_results_json"] = results_json

    saturation_json = output_dir / "saturation_summary.json"
    with open(saturation_json, "w") as f:
        json.dump(
            {
                "saturation_point": capacity.saturation_point,
                "saturation_reason": capacity.saturation_reason,
            },
            f,
            indent=2,
        )
    written["saturation_summary_json"] = saturation_json

    recommended_json = output_dir / "recommended_operating_point.json"
    with open(recommended_json, "w") as f:
        json.dump(
            {
                "recommended_operating_point": capacity.recommended_operating_point,
                "recommended_reason": capacity.recommended_reason,
            },
            f,
            indent=2,
        )
    written["recommended_operating_point_json"] = recommended_json

    # capacity_summary.* mirrors the same info in one combined artifact,
    # as required for cross-run/platform capacity comparisons.
    capacity_csv = output_dir / "capacity_summary.csv"
    with open(capacity_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["saturation_point", "saturation_reason", "recommended_operating_point", "recommended_reason"]
        )
        writer.writerow(
            [
                capacity.saturation_point,
                capacity.saturation_reason,
                capacity.recommended_operating_point,
                capacity.recommended_reason,
            ]
        )
    written["capacity_summary_csv"] = capacity_csv

    capacity_json = output_dir / "capacity_summary.json"
    with open(capacity_json, "w") as f:
        json.dump(
            {
                "saturation_point": capacity.saturation_point,
                "saturation_reason": capacity.saturation_reason,
                "recommended_operating_point": capacity.recommended_operating_point,
                "recommended_reason": capacity.recommended_reason,
                "points": [
                    {
                        "concurrency": p.concurrency,
                        "throughput_tasks_per_hour": p.throughput_tasks_per_hour,
                        "p95_latency_ms": p.p95_latency_ms,
                        "p99_latency_ms": p.p99_latency_ms,
                        "slo_passed": p.slo_passed,
                    }
                    for p in capacity.points
                ],
            },
            f,
            indent=2,
        )
    written["capacity_summary_json"] = capacity_json

    return written
