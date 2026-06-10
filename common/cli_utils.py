#!/usr/bin/env python3
"""
common/cli_utils.py — Shared argparse helpers for CWF benchmark runners.

Modelled after pnpwls/common/cli_utils.py so runner scripts share a
consistent CLI surface across all agentic benchmarks.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, Dict

import yaml


def get_base_parser(description: str = "") -> argparse.ArgumentParser:
    """Return an ArgumentParser pre-loaded with standard CWF benchmark flags.

    All benchmark run_<name>.py files should call this to obtain the base
    parser and then call ``parser.add_argument(...)`` for benchmark-specific
    flags.
    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Directory for result JSON/CSV files and run.log",
    )
    parser.add_argument(
        "--config",
        default="",
        metavar="PATH",
        help="Path to YAML config file (merges with / overrides compiled-in defaults)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        metavar="N",
        help="Number of benchmark repetitions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands/actions without executing them",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return parser


def parse_config(path: str) -> Dict[str, Any]:
    """Load a YAML config file and return it as a plain dict.

    Parameters
    ----------
    path:
        Filesystem path to a ``.yaml`` / ``.yml`` file.  An empty string
        returns an empty dict (no-op, caller uses compiled-in defaults).

    Raises
    ------
    FileNotFoundError
        If *path* is non-empty but the file does not exist.
    """
    if not path:
        return {}
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(cfg_path) as fh:
        return yaml.safe_load(fh) or {}


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger for benchmark runners.

    Call once at the start of ``main()`` before any logging calls.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
