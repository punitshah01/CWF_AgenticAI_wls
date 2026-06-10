#!/usr/bin/env python3
"""
common/metadata.py — Build run-metadata dicts for embedding in result files.

Every result JSON file produced by a CWF benchmark runner must contain a
``metadata`` block built by ``build_metadata()``.  This ensures results are
always traceable back to the exact code, platform, and config used.
"""

import datetime
import logging
from typing import Any, Dict

from .git_provenance import get_provenance_dict

log = logging.getLogger(__name__)


def build_metadata(
    config: Dict[str, Any],
    benchmark_name: str,
) -> Dict[str, Any]:
    """Return a metadata dict for embedding in the ``metadata`` block of result files.

    Combines:
    - benchmark name
    - UTC timestamp
    - git provenance (SHA, branch, repo URL)
    - system metadata (CPU topology, OS, microcode) — gracefully omitted if
      ``common.system_metadata`` is unavailable
    - the effective run config

    Parameters
    ----------
    config:
        The effective run config dict as returned by ``cli_utils.parse_config()``.
        Pass an empty dict if no config file was provided.
    benchmark_name:
        Short lowercase identifier, e.g. ``"webarena"``, ``"swe-bench"``.

    Returns
    -------
    dict
        Ready to assign to the ``"metadata"`` key of a result JSON object.

    Example result structure
    ------------------------
    ::

        {
            "metadata": build_metadata(cfg, "webarena"),
            "results": { ... }
        }
    """
    meta: Dict[str, Any] = {
        "benchmark": benchmark_name,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "provenance": get_provenance_dict(),
        "config": config,
        "system": {},
    }

    try:
        from .system_metadata import get_system_metadata  # type: ignore[import]
        meta["system"] = get_system_metadata()
    except Exception as exc:  # noqa: BLE001
        log.warning("system_metadata unavailable: %s", exc)

    return meta
