#!/usr/bin/env python3
"""
benchmarks/swe-bench/run_swe_bench.py — Canonical SWE-bench runner for CWF.

Usage:
  python3 benchmarks/swe-bench/run_swe_bench.py
  python3 benchmarks/swe-bench/run_swe_bench.py --max-workers 16 --output-dir results/swebench
  python3 benchmarks/swe-bench/run_swe_bench.py --config benchmarks/swe-bench/config/default_config.yaml
  python3 benchmarks/swe-bench/run_swe_bench.py --dry-run
"""

import logging
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from common.cli_utils import get_base_parser, parse_config, setup_logging  # noqa: E402

log = logging.getLogger(__name__)


def build_parser():
    parser = get_base_parser(description="Run SWE-bench evaluation on CWF.")
    parser.add_argument(
        "--dataset",
        default="princeton-nlp/SWE-bench_Lite",
        help="HuggingFace dataset name",
    )
    parser.add_argument(
        "--split",
        default="test",
        help="Dataset split (test | dev)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        metavar="N",
        help="Number of parallel Docker evaluation workers",
    )
    parser.add_argument(
        "--run-id",
        default="cwf_baseline",
        help="Unique run identifier for result files",
    )
    parser.add_argument(
        "--predictions-path",
        default="",
        metavar="PATH",
        help="Path to pre-generated agent predictions .jsonl file",
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
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    cfg = parse_config(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("SWE-bench run: dataset=%s max_workers=%d run_id=%s output=%s",
             args.dataset, args.max_workers, args.run_id, output_dir)

    if args.dry_run:
        log.info("[dry-run] Would invoke run.py with max_workers=%d", args.max_workers)
        return

    run_script = Path(__file__).parent / "run.py"
    cmd = [
        sys.executable, str(run_script),
        "--dataset", args.dataset,
        "--split", args.split,
        "--max-workers", str(args.max_workers),
        "--run-id", args.run_id,
        "--output-dir", str(output_dir),
    ]
    if args.predictions_path:
        cmd += ["--predictions-path", args.predictions_path]
    if args.collect_emon:
        cmd.append("--collect-emon")
    if args.verbose:
        cmd.append("--verbose")

    log.debug("Invoking: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(_REPO_ROOT))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
