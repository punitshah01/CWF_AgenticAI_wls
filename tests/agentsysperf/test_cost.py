import pytest

from common.agentsysperf.cost import compute_cost
from common.agentsysperf.models import CostModelConfig


def test_compute_only_mode_when_no_power_data():
    cfg = CostModelConfig(node_hourly_usd=10.0, runtime_s=3600)
    result = compute_cost(cfg, tasks_completed=100)
    assert result.mode == "compute_only"
    assert result.assumption is not None
    assert result.energy_cost_component_usd == 0.0
    assert result.total_run_cost_usd == pytest.approx(10.0)
    assert result.cost_per_completed_task_usd == pytest.approx(0.1)


def test_compute_plus_energy_mode():
    cfg = CostModelConfig(
        node_hourly_usd=5.0,
        runtime_s=3600,
        avg_package_power_w=200.0,
        avg_dram_power_w=40.0,
        energy_price_usd_per_kwh=0.15,
    )
    result = compute_cost(cfg, tasks_completed=50)
    assert result.mode == "compute_plus_energy"
    # energy = (240W / 1000) * 1h * 0.15 = 0.036
    assert result.energy_cost_component_usd == pytest.approx(0.036, abs=1e-6)
    assert result.total_run_cost_usd == pytest.approx(5.036, abs=1e-6)
    assert result.cost_per_completed_task_usd == pytest.approx(5.036 / 50, abs=1e-6)


def test_zero_completed_tasks_yields_none_cost_per_task():
    cfg = CostModelConfig(node_hourly_usd=10.0, runtime_s=3600)
    result = compute_cost(cfg, tasks_completed=0)
    assert result.cost_per_completed_task_usd is None
    assert result.total_run_cost_usd == pytest.approx(10.0)


def test_partial_power_data_falls_back_to_compute_only():
    cfg = CostModelConfig(node_hourly_usd=10.0, runtime_s=3600, avg_package_power_w=200.0)
    result = compute_cost(cfg, tasks_completed=10)
    assert result.mode == "compute_only"
    assert "energy_price_usd_per_kwh" in result.assumption
