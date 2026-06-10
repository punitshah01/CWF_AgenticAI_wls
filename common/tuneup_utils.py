#!/usr/bin/env python3
"""
common/tuneup_utils.py — System tuning for reproducible benchmark results.

Applies kernel-level settings (CPU governor, ASLR, NUMA) before a benchmark
run and restores them afterwards via ``restore_defaults()``.

All writes are attempted with best-effort — a permission error logs a warning
but does not abort the benchmark.
"""

import glob
import logging
import os
from typing import Dict

log = logging.getLogger(__name__)

# Stores original values so restore_defaults() can revert them
_ORIGINALS: Dict[str, str] = {}


def _read_sysfs(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _write_sysfs(path: str, value: str) -> bool:
    """Write *value* to a sysfs path.  Returns True on success."""
    try:
        with open(path, "w") as fh:
            fh.write(value)
        return True
    except PermissionError:
        log.warning("Permission denied writing %s (run as root or with sudo)", path)
        return False
    except OSError as exc:
        log.warning("Could not write %s: %s", path, exc)
        return False


def set_cpu_governor(governor: str = "performance") -> None:
    """Write *governor* to every online CPU's cpufreq scaling_governor sysfs node.

    Common values: ``performance``, ``powersave``, ``ondemand``.

    On CWF / DMR (no SMT, all P-cores) ``performance`` pins each core at max
    turbo frequency, which is the recommended setting for benchmarking.
    """
    paths = glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor")
    if not paths:
        log.warning("No cpufreq scaling_governor paths found — governor unchanged")
        return
    changed = 0
    for path in sorted(paths):
        orig = _read_sysfs(path)
        if orig:
            _ORIGINALS.setdefault(path, orig)
        if _write_sysfs(path, governor):
            changed += 1
    log.info("CPU governor set to '%s' (%d / %d CPUs)", governor, changed, len(paths))


def disable_aslr() -> None:
    """Set ``/proc/sys/kernel/randomize_va_space`` to 0 (disables ASLR).

    Reduces variance in pointer-chasing microbenchmarks.  Restore via
    ``restore_defaults()`` when the benchmark finishes.
    """
    path = "/proc/sys/kernel/randomize_va_space"
    orig = _read_sysfs(path)
    if orig:
        _ORIGINALS.setdefault(path, orig)
    if _write_sysfs(path, "0"):
        log.info("ASLR disabled (randomize_va_space → 0)")


def disable_turbo() -> None:
    """Disable Intel P-state turbo boost.

    Writes ``1`` to ``/sys/devices/system/cpu/intel_pstate/no_turbo``.
    Useful when reproducible frequency is more important than peak throughput.
    """
    path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    if not os.path.exists(path):
        log.warning("intel_pstate/no_turbo not found — turbo state unchanged")
        return
    orig = _read_sysfs(path)
    if orig:
        _ORIGINALS.setdefault(path, orig)
    if _write_sysfs(path, "1"):
        log.info("Turbo disabled (no_turbo → 1)")


def set_numa_policy(policy: str) -> None:
    """Log the intended NUMA policy.

    Actual enforcement must be done by the caller via ``numactl``.
    Example policies: ``--localalloc``, ``--interleave=all``.
    """
    log.info(
        "NUMA policy '%s': apply via: numactl %s <command>", policy, policy
    )


def restore_defaults() -> None:
    """Revert all sysfs values that were changed by this module.

    Call at the end of a benchmark run (or in a ``finally:`` block) to
    leave the system in the state it was found.
    """
    if not _ORIGINALS:
        log.debug("No tuning changes to restore")
        return
    for path, value in list(_ORIGINALS.items()):
        if _write_sysfs(path, value):
            log.info("Restored %s → %s", path, value)
    _ORIGINALS.clear()
    log.info("System tuning restored to original values")
