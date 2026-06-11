#!/usr/bin/env python3
"""
benchmarks/osworld/run.py — Run OSWorld evaluation on CWF.

Launches QEMU/KVM VMs via the OSWorld Docker controller and runs GUI tasks.

Usage:
  python3 benchmarks/osworld/run.py --model 32b --inference-cores 96
  python3 benchmarks/osworld/run.py --num-envs 4 --obs-type screenshot
  python3 benchmarks/osworld/run.py --dry-run

Arguments:
  --model            8b | 32b | 70b                          default: 32b
  --inference-cores  Cores for LLM                           default: 96
  --env-cores        Cores for QEMU VMs                      default: 64
  --num-envs         Parallel VM instances                   default: 4
  --obs-type         screenshot | accessibility_tree         default: screenshot
  --max-steps        Steps per task                          default: 15
  --llm-port         API port                                default: 8000
  --run-id           Unique label                            default: auto
  --collect-emon     Enable EMON

LLM server must be started separately:
  python3 scripts/inference/start_vllm.py --model 32b --cores 96
"""

import argparse
import os
import signal
import subprocess
import sys
import time

if sys.version_info < (3, 10):
    sys.exit(f"[ERROR] Python 3.10+ required. Current: {sys.version.split()[0]}")
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

BENCHMARK = "osworld"
BENCHMARK_DIR = Path(__file__).resolve().parent
WORKDIR = Path.home() / "cwf_agentic" / "osworld"

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
            print("\n[osworld] Stopping telemetry on interrupt …")
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
        description="OSWorld evaluation runner for CWF",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model",           default="32b")
    p.add_argument("--inference-cores", type=int, default=96)
    p.add_argument("--env-cores",       type=int, default=64)
    p.add_argument("--num-envs",        type=int, default=4,
                   help="Parallel VM instances. Each needs ~8 GB RAM.")
    p.add_argument("--obs-type",        default="screenshot",
                   choices=["screenshot", "accessibility_tree"])
    p.add_argument("--max-steps",       type=int, default=15)
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
    return f"osworld_{args.model}_{args.inference_cores}c_{args.num_envs}envs_{ts}"


def run_evaluation(args: argparse.Namespace, run_id: str) -> dict:
    base_url = f"http://localhost:{args.llm_port}/v1"

    eval_cmd = [
        sys.executable,
        str(WORKDIR / "scripts" / "python" / "run_multienv.py"),
        "--provider_name", "docker",
        "--headless",
        f"--observation_type={args.obs_type}",
        "--model", "local_llm",
        "--sleep_after_execution=3",
        f"--max_steps={args.max_steps}",
        f"--num_envs={args.num_envs}",
        "--client_password", "password",
        f"--openai_base_url={base_url}",
        f"--result_dir={WORKDIR / 'results' / run_id}",
    ]

    results = {
        "benchmark":       BENCHMARK,
        "model":           args.model,
        "inference_cores": str(args.inference_cores),
        "env_cores":       str(args.env_cores),
        "num_envs":        str(args.num_envs),
        "obs_type":        args.obs_type,
        "max_steps":       str(args.max_steps),
        "success_rate":    "0.0",
        "tasks_completed": "0",
        "tasks_total":     "369",
    }

    if args.dry_run:
        print("[dry-run] Would run:")
        print(f"  {' '.join(eval_cmd)}")
        return results

    if not WORKDIR.exists():
        print(f"[ERROR] OSWorld not found at {WORKDIR}. Run setup.py first.",
              file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    subprocess.run(eval_cmd, cwd=str(WORKDIR))
    results["total_runtime_s"] = str(round(time.time() - t0, 1))

    # Parse results
    results_file = WORKDIR / "results" / run_id / "result.json"
    if results_file.exists():
        import json
        data = json.loads(results_file.read_text())
        overall = data.get("overall", {})
        results["success_rate"]    = str(overall.get("rate", 0.0))
        results["tasks_completed"] = str(overall.get("success", 0))
        results["tasks_total"]     = str(overall.get("total", 369))

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
    print("  OSWorld Runner")
    print(f"  Run ID    : {run_id}")
    print(f"  Platform  : {platform}")
    print(f"  Model     : {args.model}  Inf-cores: {args.inference_cores}")
    print(f"  Envs      : {args.num_envs}  Obs: {args.obs_type}")
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

    print(f"\n[osworld] success_rate : {bench_results.get('success_rate')}")
    print(f"[osworld] Results      : {out_dir}")


if __name__ == "__main__":
    main()
