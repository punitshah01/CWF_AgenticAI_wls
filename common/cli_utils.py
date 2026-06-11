#!/usr/bin/env python3
"""
common/cli_utils.py — Shared argparse helpers + TeeOutput + config loading.

Mirrors pnpwls/common/cli_utils.py so runner scripts share a consistent
CLI surface across all agentic benchmarks.

Key additions vs base pnpwls:
  TeeOutput         — Mirror stdout/stderr to console + log file simultaneously
  setup_tee_logging — Open console_output.log and install TeeOutput on sys.stdout/stderr
  teardown_logging  — Restore original stdout/stderr + close log file
  load_workload_config — Load per-workload YAML from config/ with CLI override merging
  colorize_usage    — Color-tinted argparse usage string (pnpwls compat)
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# ============================================================================
# TeeOutput — mirrors pnpwls TeeOutput exactly
# ============================================================================

class TeeOutput:
    """Write output to multiple destinations simultaneously.

    Used to mirror all stdout/stderr to both the terminal and
    ``console_output.log`` within each run's output directory.

    Usage:
        log_handle = open(out_dir / "console_output.log", "w", buffering=1)
        original_stdout = sys.stdout
        sys.stdout = TeeOutput(original_stdout, log_handle)
        sys.stderr = TeeOutput(sys.stderr, log_handle)
        # ... all prints go to both terminal and file ...
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_handle.close()
    """

    def __init__(self, *outputs):
        self.outputs = outputs

    def write(self, text: str) -> None:
        for output in self.outputs:
            try:
                output.write(text)
                output.flush()
            except Exception:
                pass

    def flush(self) -> None:
        for output in self.outputs:
            try:
                output.flush()
            except Exception:
                pass

    def fileno(self) -> int:
        """Return the fileno of the first real file output (for compatibility)."""
        for output in self.outputs:
            try:
                return output.fileno()
            except Exception:
                continue
        raise io.UnsupportedOperation("fileno")


# ── Module-level state for logging teardown ──────────────────────────────────
_log_file_handle = None
_original_stdout = None
_original_stderr = None


def setup_tee_logging(log_path: Path) -> None:
    """Redirect stdout/stderr to console + log file simultaneously.

    Mirrors pnpwls StreamRunner.setup_logging() pattern.
    Call ``teardown_logging()`` in the finally block of main().

    Args:
        log_path: Absolute path to the ``console_output.log`` file.
    """
    global _log_file_handle, _original_stdout, _original_stderr

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _original_stdout = sys.stdout
    _original_stderr = sys.stderr

    _log_file_handle = open(log_path, "w", buffering=1, encoding="utf-8", errors="replace")
    sys.stdout = TeeOutput(_original_stdout, _log_file_handle)
    sys.stderr = TeeOutput(_original_stderr, _log_file_handle)


def teardown_logging() -> None:
    """Restore original stdout/stderr and close the log file.

    Call in the ``finally`` block of main() to ensure the log is flushed
    and closed even on exception or Ctrl+C.
    """
    global _log_file_handle, _original_stdout, _original_stderr

    try:
        if _original_stdout is not None:
            sys.stdout = _original_stdout
        if _original_stderr is not None:
            sys.stderr = _original_stderr
        if _log_file_handle is not None:
            _log_file_handle.flush()
            _log_file_handle.close()
    except Exception:
        pass
    finally:
        _log_file_handle = None
        _original_stdout = None
        _original_stderr = None


# ============================================================================
# Workload config loader — mirrors pnpwls pattern
# ============================================================================

def load_workload_config(workload_dir: Path, overrides: Optional[Dict] = None) -> Dict[str, Any]:
    """Load per-workload YAML config and merge CLI overrides.

    Loads ``{workload_dir}/config/workload_config.yaml`` and deep-merges
    any dict in ``overrides`` on top (CLI args take precedence).

    Args:
        workload_dir: Path to the benchmark directory (e.g. benchmarks/webarena)
        overrides:    Optional flat dict of CLI overrides (string keys, any values).

    Returns:
        Merged configuration dict.
    """
    config_path = Path(workload_dir) / "config" / "workload_config.yaml"
    config: Dict[str, Any] = {}

    if config_path.exists():
        with open(config_path) as fh:
            config = yaml.safe_load(fh) or {}
    else:
        print(f"[config] Warning: {config_path} not found — using empty config")

    if overrides:
        _deep_merge(config, overrides)

    return config


def _deep_merge(base: dict, overrides: dict) -> None:
    """In-place deep-merge overrides into base."""
    for key, val in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


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
    This configures the standard Python logger (not the TeeOutput system).
    For file+console mirroring, use setup_tee_logging() instead.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def colorize_usage(parser: argparse.ArgumentParser) -> str:
    """Return a color-tinted usage string for the given parser.

    Mirrors pnpwls/common/cli_utils.py:colorize_usage() for cross-repo
    compatibility. Returns the plain usage string if ANSI is not supported.

    Args:
        parser: ArgumentParser instance.

    Returns:
        Usage string (with ANSI colors if terminal supports it).
    """
    usage = parser.format_usage()
    if os.isatty(sys.stdout.fileno()) if hasattr(sys.stdout, 'fileno') else False:
        # Bold cyan for the "usage:" prefix
        return usage.replace("usage:", "\033[1;36musage:\033[0m", 1)
    return usage
