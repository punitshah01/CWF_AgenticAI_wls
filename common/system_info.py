#!/usr/bin/env python3
"""
System Information — Backward-Compatibility Wrapper
Re-exports CPUInfo and OSInfo; provides get_system_info() convenience function.
"""

from typing import Tuple
from .cpu_info import CPUInfo
from .os_info import OSInfo


def get_system_info() -> Tuple[CPUInfo, OSInfo]:
    """Return (CPUInfo, OSInfo) tuple."""
    return CPUInfo(), OSInfo()


__all__ = ["CPUInfo", "OSInfo", "get_system_info"]
