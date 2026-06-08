#!/usr/bin/env python3
"""
src/runner.py — Agentic AI Benchmark Runner
============================================
Orchestrates a single benchmark run with telemetry collection.

Wires together:
  common.system_metadata  — system snapshot
  common.telemetry        — EMON + RAPL + temperature
  common.csv_writer       — CSV result output
  common.json_results     — JSON result output
  common.platform_info    — platform detection

Usage:
    python3 src/runner.py --benchmark appworld \\
        --model 8b --inference-cores 64 --env-cores 32 \\
        --run-id cwf_8b_64c_1inst --collect-emon

    python3 src/runner.py --help
"""

import argparse
import sys
import time
from collections import OrderedDict
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.cpu_info        import CPUInfo
from common.os_info         import OSInfo
from common.platform_info   import detect_platform, get_platform_info
from common.system_metadata import get_system_metadata
from common.csv_writer      import write_csv_row
from common.json_results    import ResultsJsonWriter
from common.telemetry       import TelemetryManager


# ── Supported benchmarks ──────────────────────────────────────────────────────
BENCHMARKS = ["swebench", "webarena", "osworld", "appworld", "tbench"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CWF Agentic AI Benchmark Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--benchmark",       required=True, choices=BENCHMARKS)
    p.add_argument("--run-id",          default="", help="Unique run identifier")
    p.add_argument("--experiment-name", default="", help="Experiment label")
    p.add_argument("--model",           default="8b",
                   help="LLM model size: 8b | 32b | 70b (or full HF path)")
    p.add_argument("--engine",          default="llamacpp",
                   choices=["llamacpp", "vllm", "openvino"],
                   help="Inference engine")
    p.add_argument("--inference-cores", type=int, default=64,
                   help="Cores allocated to LLM inference")
    p.add_argument("--env-cores",       type=int, default=32,
                   help="Cores allocated to benchmark environment")
    p.add_argument("--num-instances",   type=int, default=1,
                   help="Parallel agent instances")
    p.add_argument("--collect-emon",    action="store_true",
                   help="Enable EMON telemetry collection")
    p.add_argument("--collect-rapl",    action="store_true", default=True,
                   help="Enable RAPL power monitoring")
    p.add_argument("--collect-temp",    action="store_true",
                   help="Enable temperature monitoring (SSMON/PTAT)")
    p.add_argument("--output-dir",      default="results",
                   help="Root output directory")
    p.add_argument("--dry-run",         action="store_true",
                   help="Print config and exit without running")
    return p.parse_args()


def build_run_id(args: argparse.Namespace) -> str:
    if args.run_id:
        return args.run_id
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{args.benchmark}_{args.model}_{args.inference_cores}c_{args.num_instances}inst_{ts}"


def main() -> None:
    args = parse_args()
    run_id = build_run_id(args)
    out_dir = Path(args.output_dir) / args.benchmark / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Platform model ────────────────────────────────────────────────────────
    cpu      = CPUInfo()
    os_info  = OSInfo()
    platform = detect_platform()
    pf_info  = get_platform_info()

    print(f"\n{'='*60}")
    print("  CWF Agentic AI Runner")
    print(f"  Benchmark : {args.benchmark}")
    print(f"  Run ID    : {run_id}")
    print(f"  Platform  : {platform} ({pf_info['short_name']})")
    print(f"  Topology  : {cpu.get_topology_summary()}")
    print(f"  Inf cores : {args.inference_cores}  Env cores: {args.env_cores}")
    print(f"  Model     : {args.model}  Engine: {args.engine}")
    print(f"  Instances : {args.num_instances}")
    print(f"  Output    : {out_dir}")
    print(f"{'='*60}\n")

    if args.dry_run:
        print("[dry-run] Exiting without running benchmark.")
        return

    sys_meta = get_system_metadata(cpu, os_info, run_id=run_id,
                                   experiment_name=args.experiment_name)

    # ── Telemetry ─────────────────────────────────────────────────────────────
    tm = TelemetryManager(
        output_dir=str(out_dir / "telemetry"),
        platform=platform,
        collect_emon=args.collect_emon,
        collect_rapl=args.collect_rapl,
        collect_temp=args.collect_temp,
    )

    # Capture platform info for results
    results_writer = ResultsJsonWriter(output_dir=out_dir, run_id=run_id)

    print("[runner] Starting telemetry …")
    tm.start(session_name=run_id)
    t_start = time.time()

    # ── Placeholder: actual benchmark invocation ──────────────────────────────
    # In production this block invokes the real benchmark runner script or
    # Python evaluation harness and collects per-task results.
    print(f"[runner] TODO: invoke {args.benchmark} evaluation harness here")
    time.sleep(2)   # stub
    benchmark_results: OrderedDict = OrderedDict()
    benchmark_results["benchmark"]       = args.benchmark
    benchmark_results["model"]           = args.model
    benchmark_results["engine"]          = args.engine
    benchmark_results["inference_cores"] = str(args.inference_cores)
    benchmark_results["env_cores"]       = str(args.env_cores)
    benchmark_results["num_instances"]   = str(args.num_instances)
    benchmark_results["tasks_completed"] = "0"     # replace with real count
    benchmark_results["primary_kpi"]     = "0.0"   # replace with real KPI
    benchmark_results["total_runtime_s"] = str(round(time.time() - t_start, 1))

    # ── Stop telemetry ────────────────────────────────────────────────────────
    print("[runner] Stopping telemetry …")
    sockets = cpu.get_sockets()
    tm.stop(process_emon=args.collect_emon, sockets=sockets)

    # ── Build common_data row ─────────────────────────────────────────────────
    common_data: OrderedDict = OrderedDict()
    common_data.update(benchmark_results)
    common_data.update(sys_meta)
    common_data["pkg_power_w"]   = str(tm.pkg_power_w)
    common_data["dram_power_w"]  = str(tm.dram_power_w)
    common_data["rapl_domains"]  = ";".join(
        f"{k}={v}" for k, v in tm.rapl_mean.items()
    )

    # ── Write CSV ─────────────────────────────────────────────────────────────
    csv_file = out_dir / "results.csv"
    write_csv_row(
        csv_file,
        header_row=list(common_data.keys()),
        value_row=list(common_data.values()),
    )
    print(f"[runner] CSV → {csv_file}")

    # ── Write JSON ────────────────────────────────────────────────────────────
    results_writer.add_row(common_data=common_data, rapl_data=tm.rapl_mean)
    results_writer.save()

    print(f"\n[runner] Run complete: {run_id}")
    print(f"[runner] Results    : {out_dir}")
    print(f"[runner] EMON ready : {tm.emon_ready}")
    print(f"[runner] Pkg power  : {tm.pkg_power_w:.1f} W")


if __name__ == "__main__":
    main()
