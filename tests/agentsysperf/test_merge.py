from pathlib import Path

from common.agentsysperf.merge import merge_run_summaries
from common.agentsysperf.models import SLOConfig
from common.agentsysperf.summary import build_run_summary, write_run_artifacts


def _make_run(root: Path, workload: str, run_id: str, active_agents: int, vcpus: int, slo_pass: bool):
    run_dir = root / workload / run_id
    slo_cfg = SLOConfig(p95_latency_ms_max=1000 if slo_pass else 1)
    summary = build_run_summary(
        workload=workload,
        run_id=run_id,
        active_agents=active_agents,
        vcpus=vcpus,
        runtime_s=3600,
        tasks_total=10,
        tasks_completed=8,
        loop_latencies_ms=[100, 200, 300],
        slo_cfg=slo_cfg,
    )
    write_run_artifacts(run_dir, summary)


def test_merge_run_summaries(tmp_path):
    _make_run(tmp_path, "tbench", "run1", active_agents=2, vcpus=64, slo_pass=True)
    _make_run(tmp_path, "tbench", "run2", active_agents=8, vcpus=64, slo_pass=True)
    _make_run(tmp_path, "webarena", "run1", active_agents=4, vcpus=128, slo_pass=False)

    out_dir = tmp_path / "agentsysperf"
    written = merge_run_summaries(tmp_path, out_dir)

    comparison_rows = (out_dir / "workload_comparison_summary.csv").read_text().strip().splitlines()
    assert len(comparison_rows) == 4  # header + 3 runs

    capacity_rows = (out_dir / "platform_capacity_summary.csv").read_text().strip().splitlines()
    assert len(capacity_rows) == 3  # header + tbench + webarena

    for path in written.values():
        assert path.exists()


def test_merge_run_summaries_no_runs(tmp_path):
    out_dir = tmp_path / "out"
    written = merge_run_summaries(tmp_path / "empty_root", out_dir)
    assert written["workload_comparison_summary_csv"].exists()
