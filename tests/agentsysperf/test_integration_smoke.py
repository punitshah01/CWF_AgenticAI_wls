"""
Integration smoke test — dry-run path + AgentSysPerf artifact schema.

Runs each benchmark's run_<workload>.py wrapper in --dry-run mode (no
external services/binaries required) and asserts the existing legacy
behavior is untouched. Also exercises the full AgentSysPerf artifact
pipeline end-to-end (build_run_summary -> write_run_artifacts) and
validates the resulting on-disk schema keys, which is what every runner
invokes in non-dry-run mode.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from common.agentsysperf.models import CostModelConfig, SLOConfig
from common.agentsysperf.summary import build_run_summary, write_run_artifacts

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_KPI_KEYS = {
    "workload", "run_id", "active_agents", "vcpus", "active_agents_per_vcpu",
    "loop_latency_p50_ms", "loop_latency_p95_ms", "loop_latency_p99_ms",
    "cost_per_completed_task_usd", "queue_depth_mean", "queue_depth_p95",
    "token_turnover_per_s", "tasks_completed_per_hour", "slo_passed",
    "slo_failure_reason",
}

REQUIRED_PHASE_NAMES = {"admit", "retrieve", "act", "decision", "commit"}


@pytest.mark.parametrize(
    "wrapper",
    [
        "benchmarks/appworld/run_appworld.py",
        "benchmarks/osworld/run_osworld.py",
        "benchmarks/swe-bench/run_swe_bench.py",
        "benchmarks/t-bench/run_t_bench.py",
        "benchmarks/webarena/run_webarena.py",
    ],
)
def test_dry_run_still_works(wrapper, tmp_path):
    """Existing dry-run CLI path must keep working unmodified (section G).

    Some wrapper scripts check for a `.setup_complete` marker unconditionally
    (pre-existing behavior, unrelated to this change) — create it temporarily
    so the dry-run path itself can be exercised end-to-end.
    """
    out_dir = tmp_path / "smoke_out"
    marker = REPO_ROOT / Path(wrapper).parent / ".setup_complete"
    marker_created = not marker.exists()
    if marker_created:
        marker.touch()
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / wrapper), "--dry-run", "--output-dir", str(out_dir)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        if marker_created:
            marker.unlink(missing_ok=True)

    assert result.returncode == 0, (
        f"{wrapper} --dry-run failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "dry-run" in (result.stdout + result.stderr).lower()


def test_agentsysperf_summary_schema_and_artifacts(tmp_path):
    """Verify the normalized KPI contract keys + phase/SLO/cost artifacts."""
    summary = build_run_summary(
        workload="tbench",
        run_id="smoke_run",
        active_agents=4,
        vcpus=64,
        runtime_s=3600,
        tasks_total=100,
        tasks_completed=75,
        loop_latencies_ms=[100 + i for i in range(200)],
        tokens_total=50000,
        queue_depth_samples=[1, 2, 3, 4],
        cost_cfg=CostModelConfig(node_hourly_usd=5.0, runtime_s=3600),
        slo_cfg=SLOConfig(p95_latency_ms_max=1000, min_success_rate=0.5),
    )

    missing = REQUIRED_KPI_KEYS - set(summary["kpi"].keys())
    assert not missing, f"Missing required normalized KPI fields: {missing}"

    phase_names = {p["phase"] for p in summary["phases"]}
    assert phase_names == REQUIRED_PHASE_NAMES

    written = write_run_artifacts(tmp_path, summary)
    for name in (
        "summary_json", "summary_csv", "phase_csv", "slo_json",
    ):
        assert name in written
        assert written[name].exists()

    data = json.loads((tmp_path / "agentsysperf_summary.json").read_text())
    assert data["kpi"]["active_agents_per_vcpu"] == pytest.approx(4 / 64)
    assert data["kpi"]["loop_latency_p95_ms"] is not None
    assert data["kpi"]["loop_latency_p99_ms"] is not None
    assert data["kpi"]["cost_per_completed_task_usd"] is not None
