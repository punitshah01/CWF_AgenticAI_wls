import pytest

from common.agentsysperf.percentiles import mean, p50, p95, p99, percentile


def test_percentile_empty_returns_none():
    assert percentile([], 95) is None
    assert p50([]) is None
    assert p95([]) is None
    assert p99([]) is None
    assert mean([]) is None


def test_percentile_single_value():
    assert percentile([42.0], 95) == 42.0


def test_percentile_known_distribution():
    values = list(range(1, 101))  # 1..100
    assert p50(values) == pytest.approx(50.5, abs=0.5)
    assert p95(values) == pytest.approx(95.05, abs=0.5)
    assert p99(values) == pytest.approx(99.01, abs=0.5)


def test_percentile_invalid_pct_raises():
    with pytest.raises(ValueError):
        percentile([1, 2, 3], 150)


def test_mean_basic():
    assert mean([1, 2, 3, 4]) == 2.5
