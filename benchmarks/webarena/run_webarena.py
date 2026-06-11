#!/usr/bin/env python3
"""
benchmarks/webarena/run_webarena.py — Canonical WebArena runner for CWF.

Uses common/cli_utils.get_base_parser() for standardised argument handling.
Benchmark-specific flags mirror run.py for drop-in compatibility.

Usage:
  python3 benchmarks/webarena/run_webarena.py --model 8b
  python3 benchmarks/webarena/run_webarena.py --model 70b --inference-cores 96
  python3 benchmarks/webarena/run_webarena.py --config benchmarks/webarena/config/default_config.yaml
  python3 benchmarks/webarena/run_webarena.py --start-idx 0 --end-idx 10 --dry-run
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
        "Run: source .venv/bin/activate",
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
            "        python3 benchmarks/webarena/setup.py",
            file=sys.stderr,
        )
        sys.exit(1)

log = logging.getLogger(__name__)


def build_parser():
    parser = get_base_parser(description="Run WebArena evaluation on CWF.")
    parser.add_argument(
        "--model",
        default="8b",
        choices=["8b", "32b", "70b"],
        help="LLM size preset (controls default inference-cores)",
    )
    parser.add_argument(
        "--inference-cores",
        default="0-63",
        metavar="RANGE",
        help="CPU core range for LLM inference (e.g. 0-63)",
    )
    parser.add_argument(
        "--env-cores",
        default="64-127",
        metavar="RANGE",
        help="CPU core range for Playwright + Docker services",
    )
    parser.add_argument(
        "--start-idx",
        type=int,
        default=0,
        help="First task index (inclusive)",
    )
    parser.add_argument(
        "--end-idx",
        type=int,
        default=812,
        help="Last task index (exclusive)",
    )
    parser.add_argument(
        "--llm-port",
        type=int,
        default=11434,
        metavar="PORT",
        help="LLM API port (11434=Ollama, 8000=llama.cpp)",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Unique label for this run (auto-generated if empty)",
    )
    parser.add_argument(
        "--collect-emon",
        action="store_true",
        help="Enable Intel EMON telemetry (requires /opt/intel/sep)",
    )
    parser.add_argument(
        "--collect-rapl",
        action="store_true",
        default=True,
        help="Enable RAPL power monitoring",
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

    log.info(
        "WebArena run: model=%s tasks=%d-%d inference_cores=%s output=%s",
        args.model, args.start_idx, args.end_idx, args.inference_cores, output_dir,
    )

    if args.dry_run:
        log.info("[dry-run] Would invoke run.py model=%s tasks=%d-%d",
                 args.model, args.start_idx, args.end_idx)
        return

    run_script = Path(__file__).parent / "run.py"
    cmd = [
        sys.executable, str(run_script),
        "--model", args.model,
        "--inference-cores", args.inference_cores,
        "--env-cores", args.env_cores,
        "--start-idx", str(args.start_idx),
        "--end-idx", str(args.end_idx),
        "--llm-port", str(args.llm_port),
        "--output-dir", str(output_dir),
    ]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    if args.collect_emon:
        cmd.append("--collect-emon")
    if args.collect_rapl:
        cmd.append("--collect-rapl")
    if args.dry_run:
        cmd.append("--dry-run")

    log.debug("Invoking: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(_REPO_ROOT))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
