#!/usr/bin/env python3
"""
benchmarks/webarena/lib/core_scheduler.py

Topology-aware core assignment for LLM + Playwright workers.

Mirrors pnpwls/{workload}/lib/core_scheduler.py pattern.
CWF-specific: no SMT (threads_per_core=1), single NUMA node.
"""
from typing import Tuple
from common.cpu_info import CPUInfo


def get_core_ranges(
    inference_cores: int,
    env_cores: int,
    cpu: CPUInfo,
) -> Tuple[str, str]:
    """Return (inference_range, env_range) as taskset CPU strings.

    Allocates inference cores starting at core 0, env cores immediately after.
    On CWF with 288 cores and no SMT, these are physical core IDs.

    Args:
        inference_cores: Number of cores for LLM inference.
        env_cores:       Number of cores for Playwright + Docker services.
        cpu:             CPUInfo instance for topology validation.

    Returns:
        Tuple of ("0-N", "N+1-M") taskset strings.

    Raises:
        ValueError: If requested cores exceed total available.
    """
    total = cpu.get_total_cores()
    if inference_cores + env_cores > total:
        raise ValueError(
            f"Requested {inference_cores} + {env_cores} = "
            f"{inference_cores + env_cores} cores > available {total}"
        )

    inf_start = 0
    inf_end   = inference_cores - 1
    env_start = inference_cores
    env_end   = inference_cores + env_cores - 1

    return (f"{inf_start}-{inf_end}", f"{env_start}-{env_end}")
