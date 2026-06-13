#!/usr/bin/env python3
"""
benchmarks/osworld/run_osworld.py — Canonical OSWorld runner for CWF.

Usage:
  python3 benchmarks/osworld/run_osworld.py
  python3 benchmarks/osworld/run_osworld.py --output-dir results/osworld --num-envs 5
  python3 benchmarks/osworld/run_osworld.py --config benchmarks/osworld/config/default_config.yaml
  python3 benchmarks/osworld/run_osworld.py --dry-run
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
            "        python3 benchmarks/osworld/setup.py",
            file=sys.stderr,
        )
        sys.exit(1)

log = logging.getLogger(__name__)


def build_parser():
    parser = get_base_parser(description="Run OSWorld agentic benchmark on CWF.")
    parser.add_argument(
        "--num-envs",
        type=int,
        default=10,
        metavar="N",
        help="Number of parallel VM environments",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=["libreoffice_calc", "libreoffice_writer", "chrome", "os"],
        help="OSWorld task domains to evaluate",
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
        "--observation-type",
        default="screenshot",
        choices=["screenshot", "accessibility_tree", "mixed"],
        help="Agent observation modality",
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

    parse_config(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("OSWorld run: num_envs=%d domains=%s output=%s",
             args.num_envs, args.domains, output_dir)

    if args.dry_run:
        log.info("[dry-run] Would invoke run.py with num_envs=%d", args.num_envs)
        return

    run_script = Path(__file__).parent / "run.py"
    cmd = [
        sys.executable, str(run_script),
        "--num-envs", str(args.num_envs),
        "--output-dir", str(output_dir),
        "--observation-type", args.observation_type,
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
