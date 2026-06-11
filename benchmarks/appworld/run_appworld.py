#!/usr/bin/env python3
"""
benchmarks/appworld/run_appworld.py — Canonical AppWorld runner for CWF.

Uses common/cli_utils.get_base_parser() for standardised argument handling
and delegates to the benchmark execution logic in run.py.

Usage:
  python3 benchmarks/appworld/run_appworld.py
  python3 benchmarks/appworld/run_appworld.py --output-dir results/appworld --iterations 3
  python3 benchmarks/appworld/run_appworld.py --config benchmarks/appworld/config/default_config.yaml
  python3 benchmarks/appworld/run_appworld.py --dry-run
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

# Allow running from repo root or from this directory
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

# Warn if not running inside a virtual environment
if sys.prefix == sys.base_prefix:
    print(
        "[WARN] Not running inside a virtual environment. "
        "Run: source .venv/bin/activate  (or the conda env from setup.py)",
        file=sys.stderr,
    )

from common.cli_utils import get_base_parser, parse_config, setup_logging  # noqa: E402
from common.metadata import build_metadata  # noqa: E402

_BENCHMARK_DIR = Path(__file__).resolve().parent
_SETUP_MARKER = _BENCHMARK_DIR / ".setup_complete"


def _check_setup_complete() -> None:
    """Exit with an actionable error if setup.py has not been run."""
    if not _SETUP_MARKER.exists():
        print(
            "[ERROR] Setup not complete. Run first:\n"
            "        python3 benchmarks/appworld/setup.py",
            file=sys.stderr,
        )
        sys.exit(1)

log = logging.getLogger(__name__)


def build_parser():
    parser = get_base_parser(
        description="Run AppWorld agentic benchmark on CWF."
    )
    parser.add_argument(
        "--dataset",
        default="test_normal",
        choices=["train", "dev", "test_normal", "test_challenge"],
        help="AppWorld dataset split",
    )
    parser.add_argument(
        "--num-instances",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel agent instances",
    )
    parser.add_argument(
        "--model",
        default="local-llm",
        help="Model name / identifier passed to the agent",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000/v1",
        help="LLM inference API base URL",
    )
    parser.add_argument(
        "--collect-emon",
        action="store_true",
        help="Enable Intel EMON telemetry (requires /opt/intel/sep)",
    )
    return parser


def main():
    _check_setup_complete()
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    cfg = parse_config(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("AppWorld run: dataset=%s instances=%d output=%s",
             args.dataset, args.num_instances, output_dir)

    if args.dry_run:
        log.info("[dry-run] Would invoke run.py with dataset=%s", args.dataset)
        return

    # Delegate to the existing run.py script (preserves all benchmark-specific logic)
    run_script = Path(__file__).parent / "run.py"
    cmd = [
        sys.executable, str(run_script),
        "--dataset", args.dataset,
        "--num-instances", str(args.num_instances),
        "--output-dir", str(output_dir),
    ]
    if args.collect_emon:
        cmd.append("--collect-emon")
    if args.verbose:
        cmd.append("--verbose")

    log.debug("Invoking: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(_REPO_ROOT))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
