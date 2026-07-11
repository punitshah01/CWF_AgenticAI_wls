import json

from common.agentsysperf.models import CostModelConfig, SLOConfig
from common.agentsysperf.summary import build_run_summary, write_run_artifacts


def test_build_run_summary_full_data():
    summary = build_run_summary(
        workload="tbench",
        run_id="tbench_test",
        active_agents=4,
        vcpus=64,
        runtime_s=3600,
        tasks_total=100,
        tasks_completed=80,
        loop_latencies_ms=[100 + i for i in range(100)],
        tokens_total=10000,
        queue_depth_samples=[1, 2, 3],
        cost_cfg=CostModelConfig(node_hourly_usd=10.0, runtime_s=3600),
        slo_cfg=SLOConfig(p95_latency_ms_max=1000, min_success_rate=0.5),
    )
    kpi = summary["kpi"]
    assert kpi["active_agents_per_vcpu"] == 4 / 64
    assert kpi["loop_latency_p50_ms"] is not None
    assert kpi["loop_latency_p95_ms"] is not None
    assert kpi["loop_latency_p99_ms"] is not None
    assert kpi["cost_per_completed_task_usd"] is not None
    assert kpi["slo_passed"] is True
    assert len(summary["phases"]) == 5


def test_build_run_summary_missing_data_does_not_crash():
    summary = build_run_summary(
        workload="osworld",
        run_id="osworld_test",
        active_agents=1,
        vcpus=0,
        runtime_s=0,
        tasks_total=0,
        tasks_completed=0,
    )
    kpi = summary["kpi"]
    assert kpi["active_agents_per_vcpu"] is None
    assert kpi["loop_latency_p95_ms"] is None
    assert kpi["slo_status"] == "not_evaluated"
    for phase in summary["phases"]:
        assert phase["source"] == "unavailable"
        assert phase["reason"] is not None


def test_write_run_artifacts_creates_all_files(tmp_path):
    summary = build_run_summary(
        workload="appworld",
        run_id="appworld_test",
        active_agents=2,
        vcpus=32,
        runtime_s=1800,
        tasks_total=50,
        tasks_completed=40,
        loop_latencies_ms=[200, 300, 400],
    )
    written = write_run_artifacts(tmp_path, summary)
    for path in written.values():
        assert path.exists()

    data = json.loads((tmp_path / "agentsysperf_summary.json").read_text())
    assert data["kpi"]["workload"] == "appworld"

    phase_csv = (tmp_path / "phase_metrics.csv").read_text()
    assert "phase,mean_ms,p95_ms,source,reason" in phase_csv
