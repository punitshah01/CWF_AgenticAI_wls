#!/usr/bin/env python3
"""
AgentSysPerf — cost-per-completed-task calculator.

compute_cost_component_usd = node_hourly_usd * (runtime_s / 3600)
energy_cost_component_usd  = (avg_package_power_w + avg_dram_power_w) / 1000
                              * (runtime_s / 3600) * energy_price_usd_per_kwh
total_cost_component_usd   = compute_cost_component_usd + energy_cost_component_usd
cost_per_completed_task_usd = total_cost_component_usd / tasks_completed

If power telemetry or an energy price are not supplied, the model falls
back to compute-only mode and annotates the assumption explicitly rather
than silently reporting a partial number as if it were complete.
"""

from common.agentsysperf.models import CostModelConfig, CostModelResult


def compute_cost(cfg: CostModelConfig, tasks_completed: int) -> CostModelResult:
    hours = cfg.runtime_s / 3600.0
    compute_cost = cfg.node_hourly_usd * hours

    energy_cost = 0.0
    mode = "compute_only"
    assumption = None

    has_power = cfg.avg_package_power_w is not None
    has_price = cfg.energy_price_usd_per_kwh is not None

    if has_power and has_price:
        # DRAM power is optional even in compute_plus_energy mode: if it is
        # not supplied we assume 0W rather than skipping the energy
        # component entirely, since package power still dominates the
        # energy cost for most agentic workloads. This slightly
        # underestimates true energy cost when DRAM telemetry is missing;
        # callers that need a more conservative estimate should supply
        # ``avg_dram_power_w`` explicitly (e.g. from RAPL).
        dram_w = cfg.avg_dram_power_w or 0.0
        total_watts = cfg.avg_package_power_w + dram_w
        kwh = (total_watts / 1000.0) * hours
        energy_cost = kwh * cfg.energy_price_usd_per_kwh
        mode = "compute_plus_energy"
    else:
        missing = []
        if not has_power:
            missing.append("avg_package_power_w")
        if not has_price:
            missing.append("energy_price_usd_per_kwh")
        assumption = (
            "Falling back to compute-only cost model; missing inputs: "
            + ", ".join(missing)
        )

    total_cost = compute_cost + energy_cost

    if tasks_completed > 0:
        cost_per_task = total_cost / tasks_completed
    else:
        cost_per_task = None

    return CostModelResult(
        total_run_cost_usd=round(total_cost, 6),
        cost_per_completed_task_usd=(
            round(cost_per_task, 6) if cost_per_task is not None else None
        ),
        compute_cost_component_usd=round(compute_cost, 6),
        energy_cost_component_usd=round(energy_cost, 6),
        total_cost_component_usd=round(total_cost, 6),
        mode=mode,
        assumption=assumption,
    )
