#!/usr/bin/env python3
"""
benchmarks/swebench/run.py — Run SWE-bench evaluation on CWF.

Invokes the SWE-bench harness with the local LLM inference server,
collects EMON/RAPL telemetry, and writes results to results/swebench/<run_id>/.

Usage:
  python3 benchmarks/swebench/run.py --model 32b --inference-cores 96
  python3 benchmarks/swebench/run.py --model 8b --inference-cores 64 --split lite
  python3 benchmarks/swebench/run.py --dry-run

Arguments:
  --model          8b | 32b | 70b | <full HF path>          default: 32b
  --inference-cores  Cores pinned to LLM                     default: 96
  --env-cores        Cores for Docker eval containers        default: 32
  --max-workers      Parallel Docker containers              default: 8
  --split            lite | verified | full                  default: lite
  --run-id           Unique label for this run               default: auto
  --llm-port         OpenAI-compatible API port              default: 8000
  --collect-emon     Enable EMON telemetry
  --collect-rapl     Enable RAPL power monitoring            default: on
  --dry-run          Print config, do not run

LLM server must be started separately:
  python3 scripts/inference/start_llamacpp.py --model 32b --cores 96
  python3 scripts/inference/start_vllm.py --model 32b --cores 96
"""

import argparse
import subprocess
import sys
import time
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

BENCHMARK = "swebench"
DATASET_MAP = {
    "lite":     "princeton-nlp/SWE-bench_Lite",
    "verified": "princeton-nlp/SWE-bench_Verified",
    "full":     "princeton-nlp/SWE-bench",
}
WORKDIR = Path.home() / "cwf_agentic" / "swebench"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="SWE-bench evaluation runner for CWF",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model",            default="32b")
    p.add_argument("--inference-cores",  type=int, default=96)
    p.add_argument("--env-cores",        type=int, default=32)
    p.add_argument("--max-workers",      type=int, default=8,
                   help="Parallel Docker containers. BKM: min(0.75*nproc, 24)")
    p.add_argument("--split",            default="lite",
                   choices=["lite", "verified", "full"])
    p.add_argument("--run-id",           default="")
    p.add_argument("--llm-port",         type=int, default=8000)
    p.add_argument("--collect-emon",     action="store_true")
    p.add_argument("--collect-rapl",     action="store_true", default=True)
    p.add_argument("--collect-temp",     action="store_true")
    p.add_argument("--dry-run",          action="store_true")
    return p.parse_args()


def build_run_id(args: argparse.Namespace) -> str:
    if args.run_id:
        return args.run_id
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"swebench_{args.split}_{args.model}_{args.inference_cores}c_{ts}"


def run_evaluation(args: argparse.Namespace, run_id: str) -> dict:
    """Invoke the SWE-bench evaluation harness. Returns result dict."""
    dataset = DATASET_MAP[args.split]
    predictions = WORKDIR / "predictions" / f"{run_id}.jsonl"
    predictions.parent.mkdir(parents=True, exist_ok=True)

    base_url = f"http://localhost:{args.llm_port}/v1"
    print(f"[swebench] Dataset   : {dataset}")
    print(f"[swebench] Workers   : {args.max_workers}")
    print(f"[swebench] LLM API   : {base_url}")
    print(f"[swebench] Workdir   : {WORKDIR}")

    if not WORKDIR.exists():
        print(f"[ERROR] SWE-bench not found at {WORKDIR}. Run setup.py first.",
              file=sys.stderr)
        if not args.dry_run:
            sys.exit(1)

    # Step 1: Generate predictions via SWE-agent
    agent_cmd = [
        sys.executable, "-m", "sweagent.run.run_batch",
        "--config", str(WORKDIR / "config" / "default.yaml"),
        "--agent.model.name", "local-llm",
        f"--agent.model.base_url={base_url}",
        "--instances.type", "swe_bench",
        f"--instances.dataset_name={dataset}",
        "--instances.split", "test",
        f"--output_dir={WORKDIR / 'trajectories' / run_id}",
    ]

    # Step 2: Evaluate predictions
    eval_cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        f"--dataset_name={dataset}",
        f"--predictions_path={predictions}",
        f"--max_workers={args.max_workers}",
        f"--run_id={run_id}",
    ]

    results = {
        "benchmark":       BENCHMARK,
        "split":           args.split,
        "dataset":         dataset,
        "model":           args.model,
        "inference_cores": str(args.inference_cores),
        "env_cores":       str(args.env_cores),
        "max_workers":     str(args.max_workers),
        "llm_port":        str(args.llm_port),
        "resolve_rate":    "0.0",
        "tasks_completed": "0",
        "tasks_total":     "0",
    }

    if args.dry_run:
        print("[dry-run] Would run:")
        print(f"  {' '.join(agent_cmd)}")
        print(f"  {' '.join(eval_cmd)}")
        return results

    t0 = time.time()
    print("[swebench] Running agent prediction ...")
    rc = subprocess.run(agent_cmd, cwd=str(WORKDIR)).returncode
    if rc != 0:
        print(f"[WARN] SWE-agent returned exit code {rc}", file=sys.stderr)

    print("[swebench] Running evaluation harness ...")
    rc = subprocess.run(eval_cmd, cwd=str(WORKDIR)).returncode

    results["total_runtime_s"] = str(round(time.time() - t0, 1))

    # Parse results JSON if available
    results_json = WORKDIR / "evaluation_results" / run_id / "results.json"
    if results_json.exists():
        import json
        data = json.loads(results_json.read_text())
        resolved = data.get("resolved_instances", [])
        total = data.get("total_instances", 0)
        results["tasks_completed"] = str(len(resolved))
        results["tasks_total"] = str(total)
        results["resolve_rate"] = f"{len(resolved)/max(total,1)*100:.2f}"

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
    print("  SWE-bench Runner")
    print(f"  Run ID    : {run_id}")
    print(f"  Platform  : {platform}")
    print(f"  Topology  : {cpu.get_topology_summary()}")
    print(f"  Model     : {args.model}  Inf-cores: {args.inference_cores}")
    print(f"  Split     : {args.split}  Workers: {args.max_workers}")
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

    csv_file = out_dir / "results.csv"
    write_csv_row(csv_file, list(common_data.keys()), list(common_data.values()))

    rw = ResultsJsonWriter(output_dir=out_dir, run_id=run_id)
    rw.add_row(common_data=common_data, rapl_data=tm.rapl_mean)
    rw.save()

    print(f"\n[swebench] resolve_rate : {bench_results.get('resolve_rate')}%")
    print(f"[swebench] Results      : {out_dir}")


if __name__ == "__main__":
    main()
