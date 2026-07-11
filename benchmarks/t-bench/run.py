#!/usr/bin/env python3
"""
benchmarks/t-bench/run.py — Run T-Bench evaluation on CWF.

Starts the T-Bench mock REST API server and runs the function-calling
evaluation harness against the local LLM.

Usage:
  python3 benchmarks/t-bench/run.py --model 8b --inference-cores 64
  python3 benchmarks/t-bench/run.py --categories tool_selection param_extraction
  python3 benchmarks/t-bench/run.py --dry-run

Arguments:
  --model            8b | 32b | 70b                          default: 8b
  --inference-cores  Cores for LLM                           default: 64
  --categories       Evaluation categories                   default: all
  --llm-port         API port                                default: 8000
  --mock-port        T-Bench mock server port                default: 9000
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
from common.cli_utils import teardown_logging

BENCHMARK = "tbench"
BENCHMARK_DIR = Path(__file__).resolve().parent
WORKDIR = Path.home() / "cwf_agentic" / "tbench"
_SETUP_MARKER = BENCHMARK_DIR / ".setup_complete"

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
            print("\n[tbench] Stopping telemetry on interrupt …")
            _TELEMETRY_MANAGER.stop(process_emon=False)
        except Exception:
            pass
    teardown_logging()


def _signal_handler(signum, frame):
    _cleanup_on_exit()
    sys.exit(130)


signal.signal(signal.SIGINT,  _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

ALL_CATEGORIES = [
    "tool_selection",
    "param_extraction",
    "multi_step",
    "error_recovery",
    "workflow_completion",
]


def parse_args() -> argparse.Namespace:
    if not _SETUP_MARKER.exists():
        print(
            "[ERROR] Setup not complete. Run first:\n"
            "        python3 benchmarks/t-bench/setup.py",
            file=sys.stderr,
        )
        sys.exit(1)
    p = argparse.ArgumentParser(
        description="T-Bench evaluation runner for CWF",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model",           default="8b")
    p.add_argument("--inference-cores", type=int, default=64)
    p.add_argument("--categories",      nargs="+", default=ALL_CATEGORIES,
                   choices=ALL_CATEGORIES,
                   help="Evaluation categories to run")
    p.add_argument("--llm-port",        type=int, default=8000)
    p.add_argument("--mock-port",       type=int, default=9000)
    p.add_argument("--run-id",          default="")
    p.add_argument("--ollama-model",    default="", metavar="NAME",
                   help="Override Ollama model name (e.g. 'llama3.1:8b'). "
                        "If empty, auto-maps from --model.")
    p.add_argument("--collect-emon",    action="store_true")
    p.add_argument("--collect-perftop", action="store_true")
    p.add_argument("--perftop-duration", type=int, default=150)
    p.add_argument("--collect-rapl",    action="store_true", default=True)
    p.add_argument("--collect-temp",    action="store_true")
    p.add_argument("--dry-run",         action="store_true")
    return p.parse_args()


def build_run_id(args: argparse.Namespace) -> str:
    if args.run_id:
        return args.run_id
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"tbench_{args.model}_{args.inference_cores}c_{ts}"


def start_mock_server(port: int) -> subprocess.Popen:
    """Start the T-Bench mock REST API server as a background process."""
    mock_script = WORKDIR / "mock_server.py"
    if not mock_script.exists():
        # Generate a minimal FastAPI mock server
        mock_script.parent.mkdir(parents=True, exist_ok=True)
        mock_script.write_text(f"""\
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="T-Bench Mock Server")

@app.get("/tools")
def list_tools():
    return [{{"name": "search", "description": "Search the web"}},
            {{"name": "calculator", "description": "Perform math"}},
            {{"name": "weather", "description": "Get weather data"}},
            {{"name": "calendar", "description": "Manage calendar events"}},
            {{"name": "email", "description": "Send/read emails"}}]

@app.post("/tools/{{tool_name}}/invoke")
def invoke_tool(tool_name: str, payload: dict = None):
    return {{"tool": tool_name, "status": "ok", "result": "mock_result"}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port={port})
""")

    return subprocess.Popen(
        [sys.executable, str(mock_script)],
        cwd=str(WORKDIR),
    )


_MODEL_MAP = {"8b": "llama3.1:8b", "32b": "llama3.1:32b", "70b": "llama3.1:70b"}


def _preflight_emon() -> None:
    sep_vars = Path("/opt/intel/sep/sep_vars.sh")
    if not sep_vars.exists():
        print("[WARN] EMON: /opt/intel/sep not found", file=sys.stderr)
        return
    r = subprocess.run(f"source {sep_vars} && emon -version",
                       shell=True, executable="/bin/bash", capture_output=True, text=True)
    if r.returncode != 0:
        print("[WARN] EMON drivers not loaded. Fix: source /opt/intel/sep/sep_vars.sh && /opt/intel/sep/insmod-sep",
              file=sys.stderr)
    else:
        print(f"[INFO] EMON ready: {r.stdout.strip().splitlines()[0]}")


def run_evaluation(args: argparse.Namespace, run_id: str) -> dict:
    _no_proxy = "localhost,127.0.0.1,0.0.0.0,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    base_url = f"http://localhost:{args.llm_port}/v1"
    mock_url = f"http://localhost:{args.mock_port}"
    out_dir_bench = WORKDIR / "results" / run_id
    out_dir_bench.mkdir(parents=True, exist_ok=True)

    # Build eval command
    eval_script = WORKDIR / "run_eval.py"
    eval_cmd = [
        sys.executable, str(eval_script),
        f"--llm-base-url={base_url}",
        f"--mock-server-url={mock_url}",
        f"--output-dir={out_dir_bench}",
        f"--categories={','.join(args.categories)}",
        "--model-name=local-llm",
    ]

    results = {
        "benchmark":         BENCHMARK,
        "model":             args.model,
        "inference_cores":   str(args.inference_cores),
        "categories":        ",".join(args.categories),
        "tool_accuracy":     "0.0",
        "param_accuracy":    "0.0",
        "workflow_complete": "0.0",
        "tasks_total":       "0",
        "tasks_passed":      "0",
    }

    if args.dry_run:
        print("[dry-run] Would run:")
        print(f"  [mock server] python3 {WORKDIR}/mock_server.py  (port {args.mock_port})")
        print(f"  {' '.join(eval_cmd)}")
        return results

    WORKDIR.mkdir(parents=True, exist_ok=True)

    # Ensure eval script exists
    if not eval_script.exists():
        eval_script.write_text("""\
\"\"\"Minimal T-Bench evaluation harness.\"\"\"
import argparse, json, pathlib, requests, sys

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--llm-base-url", required=True)
    p.add_argument("--mock-server-url", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--categories", default="tool_selection")
    p.add_argument("--model-name", default="local-llm")
    args = p.parse_args()
    out = pathlib.Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Placeholder: real harness calls LLM and validates tool calls
    result = {"tool_accuracy": 0.0, "param_accuracy": 0.0,
              "workflow_complete": 0.0, "tasks_total": 0, "tasks_passed": 0}
    (out / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))

if __name__ == "__main__":
    main()
""")

    # Build subprocess env — bypass Intel proxy for local mock server and LLM
    env = os.environ.copy()
    for _p in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(_p, None)
    env["NO_PROXY"] = _no_proxy
    env["no_proxy"] = _no_proxy

    mock_proc = start_mock_server(args.mock_port)
    time.sleep(1.5)   # allow server to start

    try:
        t0 = time.time()
        subprocess.run(eval_cmd, cwd=str(WORKDIR), env=env)
        results["total_runtime_s"] = str(round(time.time() - t0, 1))
    finally:
        mock_proc.terminate()
        mock_proc.wait()

    result_json = out_dir_bench / "result.json"
    if result_json.exists():
        import json
        data = json.loads(result_json.read_text())
        results["tool_accuracy"]     = str(data.get("tool_accuracy", 0.0))
        results["param_accuracy"]    = str(data.get("param_accuracy", 0.0))
        results["workflow_complete"] = str(data.get("workflow_complete", 0.0))
        results["tasks_total"]       = str(data.get("tasks_total", 0))
        results["tasks_passed"]      = str(data.get("tasks_passed", 0))

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
    print("  T-Bench Runner")
    print(f"  Run ID    : {run_id}")
    print(f"  Platform  : {platform}")
    print(f"  Model     : {args.model}  Inf-cores: {args.inference_cores}")
    print(f"  Categories: {', '.join(args.categories)}")
    print(f"  Output    : {out_dir}")
    print(f"{'='*60}\n")

    sys_meta = get_system_metadata(cpu, os_info, run_id=run_id,
                                   experiment_name=BENCHMARK)
    tm = TelemetryManager(
        output_dir=str(out_dir / "telemetry"),
        platform=platform,
        collect_emon=args.collect_emon,
        collect_perftop=args.collect_perftop,
        collect_rapl=args.collect_rapl,
        collect_temp=args.collect_temp,
        perftop_warmup_s=60 if args.collect_perftop else 0,
        perftop_duration_s=args.perftop_duration,
    )
    if not args.dry_run:
        if args.collect_emon:
            _preflight_emon()
        tm.start(session_name=run_id)

    bench_results = run_evaluation(args, run_id)

    if not args.dry_run:
        tm.stop(process_emon=args.collect_emon, sockets=cpu.get_sockets())

    common_data: OrderedDict = OrderedDict()
    common_data.update(bench_results)
    common_data.update(sys_meta)
    common_data["pkg_power_w"]  = str(tm.pkg_power_w)
    common_data["dram_power_w"] = str(tm.dram_power_w)
    if tm.perftop_ready:
        common_data["perftop_top_hotspot"] = tm.top_hotspot or "N/A"

    write_csv_row(out_dir / "results.csv",
                  list(common_data.keys()), list(common_data.values()))
    rw = ResultsJsonWriter(output_dir=out_dir, run_id=run_id)
    rw.add_row(common_data=common_data, rapl_data=tm.rapl_mean)
    rw.save()

    print(f"\n[tbench] tool_accuracy : {bench_results.get('tool_accuracy')}%")
    print(f"[tbench] Results       : {out_dir}")


if __name__ == "__main__":
    main()
