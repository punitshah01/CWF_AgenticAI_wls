#!/usr/bin/env python3
"""
benchmarks/webarena/run.py — Run WebArena evaluation on CWF.

Starts evaluation against self-hosted Docker web services using a local
LLM inference server and headless Playwright Chromium.

Usage:
  python3 benchmarks/webarena/run.py --model 8b                    # smoke test with Ollama
  python3 benchmarks/webarena/run.py --model 70b --inference-cores 96
  python3 benchmarks/webarena/run.py --model 8b --collect-emon     # with EMON collection
  python3 benchmarks/webarena/run.py --start-idx 0 --end-idx 10   # subset
  python3 benchmarks/webarena/run.py --dry-run

Prerequisites:
  1. Run setup.py first: python3 benchmarks/webarena/setup.py
  2. Ollama running (auto-started by setup.py) or llama-server on --llm-port
  3. For EMON: /opt/intel/sep installed + insmod drivers

Arguments:
  --model            8b | 32b | 70b                          default: 8b
  --inference-cores  Cores for LLM                           default: 96
  --env-cores        Cores for Playwright + services         default: 48
  --start-idx        First task index                        default: 0
  --end-idx          Last task index (exclusive)             default: 812
  --llm-port         API port (11434=Ollama, 8000=llama.cpp) default: 11434
  --run-id           Unique label                            default: auto
  --collect-emon     Enable EMON collection (needs SEP)
  --collect-rapl     Enable RAPL power monitoring (default: on)
  --collect-temp     Enable temperature monitoring
  --emon-warmup      Seconds to wait after workload starts before EMON begins default: 60
  --emon-duration    Seconds to collect EMON data (0 = full run)           default: 120
  --dry-run          Print config, do not run
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import warnings
from pathlib import Path

# Suppress beartype PEP 585 deprecation warnings from third-party dependencies
# (gymnasium uses typing.Mapping[...] instead of collections.abc.Mapping[...]).
try:
    from beartype.roar import BeartypeDecorHintPep585DeprecationWarning
    warnings.filterwarnings("ignore", category=BeartypeDecorHintPep585DeprecationWarning)
except ImportError:
    pass

WORKDIR = Path.home() / "cwf_agentic" / "webarena"
WEBARENA_VENV_PYTHON = Path.home() / "webarena_venv" / "bin" / "python"


def _ensure_supported_python() -> None:
    """Re-exec with the setup-created venv if the current interpreter is too old."""
    if sys.version_info >= (3, 10):
        return

    fallback_python = WEBARENA_VENV_PYTHON
    if fallback_python.exists() and Path(sys.executable).resolve() != fallback_python.resolve():
        print(
            f"[INFO] Python {sys.version.split()[0]} detected; re-launching with {fallback_python}",
            file=sys.stderr,
        )
        os.execv(str(fallback_python), [str(fallback_python), str(Path(__file__).resolve()), *sys.argv[1:]])

    sys.exit(
        "[ERROR] Python 3.10+ required. "
        f"Current: {sys.version.split()[0]}. "
        "Run 'source ~/activate_webarena.sh' or re-run setup.py to create ~/webarena_venv."
    )


_ensure_supported_python()

from collections import OrderedDict
from datetime import datetime

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

BENCHMARK = "webarena"
BENCHMARK_DIR = Path(__file__).resolve().parent
_SETUP_MARKER = BENCHMARK_DIR / ".setup_complete"

# ── Global state for signal-handler cleanup (mirrors pnpwls pattern) ─────────
_TELEMETRY_MANAGER = None
_CLEANUP_CALLED = False


def _cleanup_on_exit() -> None:
    """Stop telemetry gracefully on SIGINT/SIGTERM."""
    global _TELEMETRY_MANAGER, _CLEANUP_CALLED
    if _CLEANUP_CALLED:
        return
    _CLEANUP_CALLED = True
    if _TELEMETRY_MANAGER is not None:
        try:
            print("\n[webarena] Stopping telemetry on interrupt …")
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
    if not _SETUP_MARKER.exists():
        print(
            "[ERROR] Setup not complete. Run first:\n"
            "        python3 benchmarks/webarena/setup.py",
            file=sys.stderr,
        )
        sys.exit(1)
    p = argparse.ArgumentParser(
        description="WebArena evaluation runner for CWF",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model",           default="8b",
                    help="Model shortcut: 8b | 32b | 70b (maps to llama3:<size>)")
    p.add_argument("--ollama-model",    default="", metavar="NAME",
                    help="Override the Ollama model name (e.g. 'llama3.1:70b'). "
                         "If empty, auto-maps from --model (llama3:8b / 32b / 70b).")
    p.add_argument("--inference-cores", type=int, default=96)
    p.add_argument("--env-cores",       type=int, default=48)
    p.add_argument("--start-idx",       type=int, default=0)
    p.add_argument("--end-idx",         type=int, default=812)
    p.add_argument("--llm-port",        type=int, default=11434,
                    help="LLM API port (11434=Ollama, 8000=llama.cpp)")
    p.add_argument("--run-id",          default="")
    p.add_argument("--collect-emon",    action="store_true",
                    help="Enable EMON collection (requires /opt/intel/sep)")
    p.add_argument("--collect-rapl",    action="store_true", default=True)
    p.add_argument("--collect-temp",    action="store_true")
    p.add_argument("--emon-warmup",     type=int, default=60,
                    help="Seconds to wait after workload starts before EMON collection begins (skip cold-start transient)")
    p.add_argument("--emon-duration",   type=int, default=180,
                    help="Seconds to collect EMON data; 0 = collect until workload ends (default: 180s = 3 min steady-state)")
    p.add_argument("--dry-run",         action="store_true")
    return p.parse_args()


_MODEL_MAP = {"8b": "llama3.1:8b", "32b": "llama3.1:32b", "70b": "llama3.1:70b"}


def _resolve_model_name(args: argparse.Namespace) -> str:
    """Return the final model name to pass to Ollama/OpenAI-compat API."""
    if args.ollama_model:
        return args.ollama_model
    return _MODEL_MAP.get(args.model, args.model)


def _preflight_playwright() -> None:
    """Abort early if playwright is not importable inside this venv."""
    check = subprocess.run(
        [sys.executable, "-c", "import playwright"],
        capture_output=True,
    )
    if check.returncode != 0:
        print(
            "[ERROR] 'playwright' is not installed in this venv.\n"
            "  Fix: run the following two commands, then retry:\n"
            f"    {sys.executable.replace('python', 'pip')} install playwright==1.32.1\n"
            f"    {sys.executable.replace('python', 'playwright')} install chromium",
            file=sys.stderr,
        )
        sys.exit(1)


def _preflight_ollama_model(args: argparse.Namespace, model_name: str) -> None:
    """Check that the requested model exists in Ollama; print available models if not."""
    try:
        url = f"http://localhost:{args.llm_port}/api/tags"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        available = [m["name"] for m in data.get("models", [])]
    except Exception:
        # Ollama not reachable — let the evaluation surface the error naturally
        return

    if not available:
        return

    # Exact match (with or without :latest suffix)
    def _matches(name: str) -> bool:
        norm = name if ":" in name else f"{name}:latest"
        target = model_name if ":" in model_name else f"{model_name}:latest"
        return norm == target

    if any(_matches(a) for a in available):
        return  # all good

    print(
        f"[ERROR] Model '{model_name}' not found in Ollama.\n"
        f"  Available models: {', '.join(available)}\n"
        f"  Use --ollama-model to specify the exact name, e.g.:\n"
        f"    --ollama-model {available[0]}",
        file=sys.stderr,
    )
    sys.exit(1)


def build_run_id(args: argparse.Namespace) -> str:
    if args.run_id:
        return args.run_id
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    n = args.end_idx - args.start_idx
    return f"webarena_{args.model}_{args.inference_cores}c_{n}tasks_{ts}"


def run_evaluation(args: argparse.Namespace, run_id: str) -> dict:
    """Invoke WebArena run.py. Returns result dict."""
    results_dir = WORKDIR / "results" / run_id
    results_dir.mkdir(parents=True, exist_ok=True)

    base_url = f"http://localhost:{args.llm_port}/v1"

    # Resolve and validate model name before touching any env vars
    model_name = _resolve_model_name(args)

    # Source endpoint env vars from the setup-generated file
    env = os.environ.copy()
    env_file = Path.home() / ".cwf_webarena_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("export ") and "=" in line:
                kv = line[len("export "):]
                key, _, val = kv.partition("=")
                env[key] = val.strip('"')
    else:
        print(f"[WARN] {env_file} not found. Run setup.py first.", file=sys.stderr)

    # Set OpenAI env vars for the legacy openai==0.27.0 SDK used by WebArena
    # (WebArena's run.py does NOT accept --openai_api_base as a CLI arg)
    env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "dummy")
    env["OPENAI_API_BASE"] = base_url

    # Ensure WebArena's internal subprocess calls (e.g. auto_login.py) use the
    # venv python — not the system python3 which lacks playwright.
    # Prepending the venv bin to PATH means `python3` resolves to the venv python.
    venv_bin = str(WEBARENA_VENV_PYTHON.parent)
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = str(WEBARENA_VENV_PYTHON.parent.parent)

    eval_cmd = [
        sys.executable, str(WORKDIR / "run.py"),
        "--instruction_path",
        str(WORKDIR / "agent" / "prompts" / "jsons" / "p_cot_id_actree_2s.json"),
        f"--test_start_idx={args.start_idx}",
        f"--test_end_idx={args.end_idx}",
        "--provider", "openai",
        "--model", model_name,
        "--temperature", "0.1",
        "--max_tokens", "512",
        f"--result_dir={results_dir}",
    ]

    n_tasks = args.end_idx - args.start_idx
    results = {
        "benchmark":       BENCHMARK,
        "model":           args.model,
        "inference_cores": str(args.inference_cores),
        "env_cores":       str(args.env_cores),
        "start_idx":       str(args.start_idx),
        "end_idx":         str(args.end_idx),
        "n_tasks":         str(n_tasks),
        "success_rate":    "0.0",
        "tasks_completed": "0",
    }

    if args.dry_run:
        print("[dry-run] Would run:")
        print(f"  source {env_file}")
        print(f"  taskset -c {args.inference_cores}-{args.inference_cores+args.env_cores-1} \\")
        print(f"    {' '.join(eval_cmd)}")
        return results

    if not WORKDIR.exists():
        print(f"[ERROR] WebArena not found at {WORKDIR}. Run setup.py first.",
              file=sys.stderr)
        sys.exit(1)

    t0 = time.time()

    # Pin evaluation workers to env cores
    if args.env_cores > 0:
        cpu_start = args.inference_cores
        cpu_end = cpu_start + args.env_cores - 1
        cmd = ["taskset", "-c", f"{cpu_start}-{cpu_end}"] + eval_cmd
    else:
        cmd = eval_cmd

    subprocess.run(cmd, cwd=str(WORKDIR), env=env)
    results["total_runtime_s"] = str(round(time.time() - t0, 1))

    # Parse result JSON if available
    import json
    for jf in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text())
            if "success_rate" in data:
                results["success_rate"] = str(data["success_rate"])
            if "num_success" in data:
                results["tasks_completed"] = str(data["num_success"])
            break
        except Exception:
            continue

    return results


def main() -> None:
    global _TELEMETRY_MANAGER

    args = parse_args()
    run_id = build_run_id(args)
    out_dir = REPO_ROOT / "results" / BENCHMARK / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pre-flight: fail fast before starting telemetry or touching EMON
    if not args.dry_run:
        _preflight_playwright()
        _preflight_ollama_model(args, _resolve_model_name(args))

    # TeeOutput: mirror all stdout/stderr to console_output.log (pnpwls pattern)
    if not args.dry_run:
        setup_tee_logging(out_dir / "console_output.log")

    try:
        cpu = CPUInfo()
        os_info = OSInfo()
        platform = detect_platform()
        model_label = _resolve_model_name(args)

        print(f"\n{'='*60}")
        print("  WebArena Runner")
        print(f"  Run ID    : {run_id}")
        print(f"  Platform  : {platform}")
        print(f"  Model     : {args.model} ({model_label})  Inf-cores: {args.inference_cores}")
        print(f"  Tasks     : {args.start_idx}..{args.end_idx}")
        print(f"  Output    : {out_dir}")
        if args.collect_emon:
            dur_label = f"{args.emon_duration}s" if args.emon_duration > 0 else "full run"
            print(f"  EMON      : warmup={args.emon_warmup}s, collect {dur_label}")
        print(f"{'='*60}\n")

        sys_meta = get_system_metadata(cpu, os_info, run_id=run_id,
                                       experiment_name=BENCHMARK)
        emon_duration = args.emon_duration if args.emon_duration > 0 else None
        tm = TelemetryManager(
            output_dir=str(out_dir / "telemetry"),
            platform=platform,
            collect_emon=args.collect_emon,
            collect_rapl=args.collect_rapl,
            collect_temp=args.collect_temp,
            emon_warmup_s=args.emon_warmup,
            emon_duration_s=emon_duration,
        )
        _TELEMETRY_MANAGER = tm

        if not args.dry_run:
            tm.start(session_name=run_id)

        bench_results = run_evaluation(args, run_id)

        if not args.dry_run:
            print(f"\n[telemetry] Stopping collectors and processing EMON...")
            tm.stop(process_emon=args.collect_emon, sockets=cpu.get_sockets())
            print(f"[telemetry] Collection complete.")

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

        # Final Summary
        print(f"\n{'='*70}")
        print("  WebArena Run Summary")
        print(f"{'='*70}")
        print(f"  Run ID           : {run_id}")
        print(f"  Tasks Completed  : {bench_results.get('tasks_completed', 'N/A')}/{bench_results.get('n_tasks', 'N/A')}")
        print(f"  Success Rate     : {bench_results.get('success_rate', 'N/A')}%")
        print(f"  Total Runtime    : {bench_results.get('total_runtime_s', 'N/A')}s")
        print(f"\n  Power Metrics (RAPL):")
        print(f"    Package Power  : {tm.pkg_power_w:.1f}W (mean)")
        print(f"    DRAM Power     : {tm.dram_power_w:.1f}W (mean)")
        if args.collect_emon:
            print(f"\n  EMON Collection  : {tm.emon_ready}")
            if tm.emon_output_dir:
                print(f"    Output Dir     : {tm.emon_output_dir}")
                csv_files = list(tm.emon_output_dir.glob("*.csv"))
                if csv_files:
                    print(f"    CSV Files      : {len(csv_files)} generated")
                    for cf in csv_files[:3]:
                        print(f"                   - {cf.name}")
        print(f"\n  Results Location : {out_dir}")
        print(f"{'='*70}\n")

    except KeyboardInterrupt:
        print("\n\n[webarena] Interrupted by user.")
    except Exception as exc:
        print(f"\n[webarena] Fatal error: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        teardown_logging()


if __name__ == "__main__":
    main()
