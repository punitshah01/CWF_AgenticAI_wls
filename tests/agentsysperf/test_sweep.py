import json

from common.agentsysperf.sweep import run_concurrency_sweep, write_sweep_artifacts


def fake_run_fn(concurrency):
    # Simulate saturation past concurrency=4: latency blows up, SLA fails.
    if concurrency <= 4:
        return {
            "throughput_tasks_per_hour": concurrency * 50.0,
            "loop_latencies_ms": [100.0 * concurrency] * 20,
            "slo_passed": True,
        }
    return {
        "throughput_tasks_per_hour": 210.0,
        "loop_latencies_ms": [5000.0] * 20,
        "slo_passed": False,
    }


def test_run_concurrency_sweep_basic():
    points = run_concurrency_sweep(fake_run_fn, [1, 2, 4, 8], repetitions=2)
    assert len(points) == 4
    assert points[0].concurrency == 1
    assert points[-1].slo_passed is False


def test_write_sweep_artifacts(tmp_path):
    points = run_concurrency_sweep(fake_run_fn, [1, 2, 4, 8])
    written = write_sweep_artifacts(tmp_path, points)
    for path in written.values():
        assert path.exists()

    saturation = json.loads((tmp_path / "saturation_summary.json").read_text())
    assert saturation["saturation_point"] == 8

    recommended = json.loads((tmp_path / "recommended_operating_point.json").read_text())
    assert recommended["recommended_operating_point"] in (1, 2, 4)
