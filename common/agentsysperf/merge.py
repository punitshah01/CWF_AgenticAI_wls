#!/usr/bin/env python3
"""
AgentSysPerf — cross-run merge utility.

Aggregates ``agentsysperf_summary.json`` files from multiple run folders
into platform/SKU-decision-ready artifacts:

  * workload_comparison_summary.csv — one row per run, all workloads mixed
  * platform_capacity_summary.csv   — one row per workload with best-seen
                                       active_agents_per_vcpu among SLO-passing
                                       runs plus its p95/p99/cost.

Usable as a library (``merge_run_summaries``) or as a CLI::

    python3 -m common.agentsysperf.merge --runs-root results --out-dir results/agentsysperf
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def _load_summaries(runs_root: Path) -> List[Dict]:
    summaries = []
    for summary_file in sorted(runs_root.rglob("agentsysperf_summary.json")):
        try:
            data = json.loads(summary_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        kpi = data.get("kpi", {})
        if kpi:
            kpi = dict(kpi)
            kpi["_source_file"] = str(summary_file)
            summaries.append(kpi)
    return summaries


def merge_run_summaries(runs_root: Path, out_dir: Path) -> Dict[str, Path]:
    runs_root = Path(runs_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}

    rows = _load_summaries(runs_root)

    comparison_csv = out_dir / "workload_comparison_summary.csv"
    if rows:
        fieldnames = sorted({k for row in rows for k in row.keys()})
        with open(comparison_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(comparison_csv, "w", newline="") as f:
            f.write("workload,run_id\n")
    written["workload_comparison_summary_csv"] = comparison_csv

    # Best SLO-passing operating point per workload, ranked by
    # active_agents_per_vcpu (higher is better density under SLO).
    by_workload: Dict[str, List[Dict]] = {}
    for row in rows:
        by_workload.setdefault(row.get("workload", "unknown"), []).append(row)

    capacity_rows = []
    for workload, wrows in sorted(by_workload.items()):
        passing = [r for r in wrows if r.get("slo_passed")]
        pool = passing or wrows
        best = max(
            pool,
            key=lambda r: (r.get("active_agents_per_vcpu") or 0),
            default=None,
        )
        if best is None:
            continue
        capacity_rows.append(
            {
                "workload": workload,
                "best_active_agents_per_vcpu": best.get("active_agents_per_vcpu"),
                "loop_latency_p95_ms": best.get("loop_latency_p95_ms"),
                "loop_latency_p99_ms": best.get("loop_latency_p99_ms"),
                "cost_per_completed_task_usd": best.get("cost_per_completed_task_usd"),
                "slo_passed": best.get("slo_passed"),
                "run_id": best.get("run_id"),
            }
        )

    capacity_csv = out_dir / "platform_capacity_summary.csv"
    with open(capacity_csv, "w", newline="") as f:
        fieldnames = [
            "workload",
            "best_active_agents_per_vcpu",
            "loop_latency_p95_ms",
            "loop_latency_p99_ms",
            "cost_per_completed_task_usd",
            "slo_passed",
            "run_id",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(capacity_rows)
    written["platform_capacity_summary_csv"] = capacity_csv

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge AgentSysPerf run summaries across folders.")
    parser.add_argument("--runs-root", default="results", help="Root directory to search recursively.")
    parser.add_argument("--out-dir", default="results/agentsysperf", help="Where to write merged artifacts.")
    args = parser.parse_args()

    written = merge_run_summaries(Path(args.runs_root), Path(args.out_dir))
    for name, path in written.items():
        print(f"[agentsysperf.merge] wrote {name} -> {path}")


if __name__ == "__main__":
    main()
