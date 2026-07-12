from common.agentsysperf.queue_stats import (
    active_agents_per_vcpu,
    queue_depth_stats,
    tasks_completed_per_hour,
    token_turnover_per_s,
)


def test_active_agents_per_vcpu_basic():
    assert active_agents_per_vcpu(8, 64) == 0.125


def test_active_agents_per_vcpu_zero_vcpus():
    assert active_agents_per_vcpu(8, 0) is None


def test_token_turnover_per_s():
    assert token_turnover_per_s(3600, 3600) == 1.0
    assert token_turnover_per_s(100, 0) is None


def test_tasks_completed_per_hour():
    assert tasks_completed_per_hour(10, 3600) == 10.0
    assert tasks_completed_per_hour(10, 0) is None


def test_queue_depth_stats_empty():
    stats = queue_depth_stats([])
    assert stats["queue_depth_mean"] is None
    assert stats["queue_depth_p95"] is None


def test_queue_depth_stats_basic():
    stats = queue_depth_stats([1, 2, 3, 4, 5])
    assert stats["queue_depth_mean"] == 3.0
    assert stats["queue_depth_p95"] is not None
