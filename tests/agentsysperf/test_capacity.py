from common.agentsysperf.capacity import SweepPoint, detect_capacity


def test_saturation_on_first_slo_failure():
    points = [
        SweepPoint(concurrency=1, throughput_tasks_per_hour=100, p95_latency_ms=500, p99_latency_ms=600, slo_passed=True),
        SweepPoint(concurrency=2, throughput_tasks_per_hour=190, p95_latency_ms=550, p99_latency_ms=650, slo_passed=True),
        SweepPoint(concurrency=4, throughput_tasks_per_hour=250, p95_latency_ms=2000, p99_latency_ms=5000, slo_passed=False),
    ]
    summary = detect_capacity(points)
    assert summary.saturation_point == 4
    assert "SLA failed" in summary.saturation_reason
    assert summary.recommended_operating_point == 2


def test_recommended_point_prefers_stable_tail_latency():
    points = [
        SweepPoint(concurrency=1, throughput_tasks_per_hour=100, p95_latency_ms=100, p99_latency_ms=110, slo_passed=True),
        SweepPoint(concurrency=2, throughput_tasks_per_hour=195, p95_latency_ms=110, p99_latency_ms=300, slo_passed=True),
    ]
    summary = detect_capacity(points, tail_ratio_max=1.5)
    # concurrency=2 has p99/p95 ratio ~2.7 > 1.5 -> unstable, falls back to 1
    assert summary.recommended_operating_point == 1


def test_marginal_gain_collapse_detected():
    points = [
        SweepPoint(concurrency=1, throughput_tasks_per_hour=100, p95_latency_ms=100, p99_latency_ms=110, slo_passed=True),
        SweepPoint(concurrency=2, throughput_tasks_per_hour=195, p95_latency_ms=110, p99_latency_ms=120, slo_passed=True),
        SweepPoint(concurrency=4, throughput_tasks_per_hour=200, p95_latency_ms=120, p99_latency_ms=130, slo_passed=True),
    ]
    summary = detect_capacity(points, marginal_gain_floor=0.10)
    assert summary.saturation_point == 4


def test_empty_points_returns_none():
    summary = detect_capacity([])
    assert summary.saturation_point is None
    assert summary.recommended_operating_point is None
    assert summary.saturation_reason is not None
