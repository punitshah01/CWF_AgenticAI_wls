import json

from common.agentsysperf.sweep import run_concurrency_sweep, write_sweep_artifacts


def fake_run_fn(concurrency):
    # Simulate saturation past concurrency=4: latency blows up, SLA fails.
    # Sweep points are [1, 2, 4, 8], so concurrency=8 is expected to be the
    # first point where slo_passed=False -> saturation_point should be 8.
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


def test_run_concurrency_sweep_averages_repetitions():
    call_count = {"n": 0}

    def variable_run_fn(concurrency):
        call_count["n"] += 1
        # Alternate between 100 and 200 tasks/hr across repetitions so the
        # aggregated point should equal the average (150.0), proving
        # repetitions are averaged rather than just the last one kept.
        throughput = 100.0 if call_count["n"] % 2 == 1 else 200.0
        return {
            "throughput_tasks_per_hour": throughput,
            "loop_latencies_ms": [100.0],
            "slo_passed": True,
        }

    points = run_concurrency_sweep(variable_run_fn, [1], repetitions=2)
    assert len(points) == 1
    assert points[0].throughput_tasks_per_hour == 150.0
    assert call_count["n"] == 2


def test_write_sweep_artifacts(tmp_path):
    points = run_concurrency_sweep(fake_run_fn, [1, 2, 4, 8])
    written = write_sweep_artifacts(tmp_path, points)
    for path in written.values():
        assert path.exists()

    saturation = json.loads((tmp_path / "saturation_summary.json").read_text())
    assert saturation["saturation_point"] == 8

    recommended = json.loads((tmp_path / "recommended_operating_point.json").read_text())
    assert recommended["recommended_operating_point"] in (1, 2, 4)
