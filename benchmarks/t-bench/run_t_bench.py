#!/usr/bin/env python3
"""
benchmarks/t-bench/run_t_bench.py — Canonical T-Bench runner for CWF.

Usage:
  python3 benchmarks/t-bench/run_t_bench.py
  python3 benchmarks/t-bench/run_t_bench.py --output-dir results/tbench --iterations 5
  python3 benchmarks/t-bench/run_t_bench.py --config benchmarks/t-bench/config/default_config.yaml
  python3 benchmarks/t-bench/run_t_bench.py --dry-run
"""

import logging
import subprocess
import sys
from pathlib import Path

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

_BENCHMARK_DIR = Path(__file__).resolve().parent
_SETUP_MARKER = _BENCHMARK_DIR / ".setup_complete"


def _check_setup_complete() -> None:
    """Exit with an actionable error if setup.py has not been run."""
    if not _SETUP_MARKER.exists():
        print(
            "[ERROR] Setup not complete. Run first:\n"
            "        python3 benchmarks/t-bench/setup.py",
            file=sys.stderr,
        )
        sys.exit(1)

log = logging.getLogger(__name__)


def build_parser():
    parser = get_base_parser(description="Run T-Bench tool-calling evaluation on CWF.")
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
        "--server-port",
        type=int,
        default=8001,
        metavar="PORT",
        help="T-Bench mock API server port",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        metavar="N",
        help="Maximum tool calls per task",
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

    log.info("T-Bench run: model=%s iterations=%d output=%s",
             args.model, args.iterations, output_dir)

    if args.dry_run:
        log.info("[dry-run] Would invoke run.py on port=%d", args.server_port)
        return

    run_script = Path(__file__).parent / "run.py"
    cmd = [
        sys.executable, str(run_script),
        "--server-port", str(args.server_port),
        "--max-steps", str(args.max_steps),
        "--output-dir", str(output_dir),
        "--iterations", str(args.iterations),
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
