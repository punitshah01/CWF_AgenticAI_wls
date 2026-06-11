#!/usr/bin/env python3
"""
benchmarks/appworld/run.py — Run AppWorld evaluation on CWF.

Runs AppWorld agent against dev / test_normal / test_challenge datasets
using the local LLM inference server.

Usage:
  python3 benchmarks/appworld/run.py --model 8b --inference-cores 64
  python3 benchmarks/appworld/run.py --dataset test_normal --num-instances 4
  python3 benchmarks/appworld/run.py --dry-run

Arguments:
  --model            8b | 32b | 70b                          default: 8b
  --inference-cores  Cores for LLM                           default: 64
  --env-cores        Cores per AppWorld instance             default: 8
  --num-instances    Parallel agent instances                default: 1
  --dataset          dev | test_normal | test_challenge      default: dev
  --agent            AppWorld agent name                     default: simplified_function_calling_agent
  --llm-port         API port                                default: 8000
  --run-id           Unique label                            default: auto
  --collect-emon     Enable EMON

LLM server must be started separately:
  python3 scripts/inference/start_llamacpp.py --model 8b --cores 64
"""

import argparse
import os
import signal
import subprocess
import sys
import time

if sys.version_info < (3, 11):
    sys.exit(f"[ERROR] Python 3.11+ required for AppWorld. Current: {sys.version.split()[0]}")
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from common.cpu_info import CPUInfo
from common.os_info import OSInfo
from common.platform_info import detect_platform
from common.system_metadata import get_system_metadata
from common.csv_writer import write_csv_row
from common.json_results import ResultsJsonWriter
from common.telemetry import TelemetryManager
from common.cli_utils import setup_tee_logging, teardown_logging, load_workload_config

BENCHMARK = "appworld"
BENCHMARK_DIR = Path(__file__).resolve().parent

# ── Global state for signal-handler cleanup ───────────────────────────────────
_TELEMETRY_MANAGER = None
_CLEANUP_CALLED = False


def _cleanup_on_exit() -> None:
    global _TELEMETRY_MANAGER, _CLEANUP_CALLED
    if _CLEANUP_CALLED:
        return
    _CLEANUP_CALLED = True
    if _TELEMETRY_MANAGER is not None:
        try:
            print("\n[appworld] Stopping telemetry on interrupt …")
            _TELEMETRY_MANAGER.stop(process_emon=False)
        except Exception:
            pass
    teardown_logging()


def _signal_handler(signum, frame):
    _cleanup_on_exit()
    sys.exit(130)


signal.signal(signal.SIGINT,  _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AppWorld evaluation runner for CWF",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model",           default="8b")
    p.add_argument("--inference-cores", type=int, default=64)
    p.add_argument("--env-cores",       type=int, default=8)
    p.add_argument("--num-instances",   type=int, default=1)
    p.add_argument("--dataset",         default="dev",
                   choices=["dev", "test_normal", "test_challenge"])
    p.add_argument("--agent",           default="simplified_function_calling_agent")
    p.add_argument("--llm-port",        type=int, default=8000)
    p.add_argument("--run-id",          default="")
    p.add_argument("--collect-emon",    action="store_true")
    p.add_argument("--collect-rapl",    action="store_true", default=True)
    p.add_argument("--collect-temp",    action="store_true")
    p.add_argument("--dry-run",         action="store_true")
    return p.parse_args()


def build_run_id(args: argparse.Namespace) -> str:
    if args.run_id:
        return args.run_id
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"appworld_{args.dataset}_{args.model}_{args.inference_cores}c_{ts}"


def run_evaluation(args: argparse.Namespace, run_id: str) -> dict:
    base_url = f"http://localhost:{args.llm_port}/v1"

    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = base_url
    env["OPENAI_API_KEY"]  = "not-needed"

    run_cmd = [
        "appworld", "run", "auto",
        f"--agent-name={args.agent}",
        "--model-name=local-llm",
        f"--dataset-name={args.dataset}",
        f"--experiment-name={run_id}",
    ]
    eval_cmd = [
        "appworld", "evaluate", run_id, args.dataset,
    ]

    results = {
        "benchmark":              BENCHMARK,
        "dataset":                args.dataset,
        "model":                  args.model,
        "inference_cores":        str(args.inference_cores),
        "env_cores":              str(args.env_cores),
        "num_instances":          str(args.num_instances),
        "agent":                  args.agent,
        "task_completion_rate":   "0.0",
        "sgc_score":              "0.0",
        "tasks_completed":        "0",
    }

    if args.dry_run:
        print("[dry-run] Would run:")
        print(f"  OPENAI_BASE_URL={base_url}")
        print(f"  {' '.join(run_cmd)}")
        print(f"  {' '.join(eval_cmd)}")
        return results

    t0 = time.time()
    print(f"[appworld] Running agent on {args.dataset} ...")
    subprocess.run(run_cmd, env=env)

    print("[appworld] Evaluating ...")
    subprocess.run(eval_cmd, env=env)

    results["total_runtime_s"] = str(round(time.time() - t0, 1))

    # Parse evaluation output if available
    import json
    eval_json = Path.home() / "appworld" / "experiments" / run_id / "evaluation.json"
    if eval_json.exists():
        data = json.loads(eval_json.read_text())
        results["task_completion_rate"] = str(data.get("task_completion_rate", 0.0))
        results["sgc_score"]            = str(data.get("sgc", 0.0))
        results["tasks_completed"]      = str(data.get("num_completed", 0))

    return results


def main() -> None:
    args = parse_args()
    run_id = build_run_id(args)
    out_dir = REPO_ROOT / "results" / BENCHMARK / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cpu = CPUInfo()
    os_info = OSInfo()
    platform = detect_platform()

    print(f"\n{'='*60}")
    print("  AppWorld Runner")
    print(f"  Run ID    : {run_id}")
    print(f"  Platform  : {platform}")
    print(f"  Model     : {args.model}  Inf-cores: {args.inference_cores}")
    print(f"  Dataset   : {args.dataset}  Instances: {args.num_instances}")
    print(f"  Output    : {out_dir}")
    print(f"{'='*60}\n")

    sys_meta = get_system_metadata(cpu, os_info, run_id=run_id,
                                   experiment_name=BENCHMARK)
    tm = TelemetryManager(
        output_dir=str(out_dir / "telemetry"),
        platform=platform,
        collect_emon=args.collect_emon,
        collect_rapl=args.collect_rapl,
        collect_temp=args.collect_temp,
    )
    if not args.dry_run:
        tm.start(session_name=run_id)

    bench_results = run_evaluation(args, run_id)

    if not args.dry_run:
        tm.stop(process_emon=args.collect_emon, sockets=cpu.get_sockets())

    common_data: OrderedDict = OrderedDict()
    common_data.update(bench_results)
    common_data.update(sys_meta)
    common_data["pkg_power_w"]  = str(tm.pkg_power_w)
    common_data["dram_power_w"] = str(tm.dram_power_w)

    write_csv_row(out_dir / "results.csv",
                  list(common_data.keys()), list(common_data.values()))
    rw = ResultsJsonWriter(output_dir=out_dir, run_id=run_id)
    rw.add_row(common_data=common_data, rapl_data=tm.rapl_mean)
    rw.save()

    print(f"\n[appworld] task_completion_rate : {bench_results.get('task_completion_rate')}%")
    print(f"[appworld] sgc_score            : {bench_results.get('sgc_score')}")
    print(f"[appworld] Results              : {out_dir}")


if __name__ == "__main__":
    main()
