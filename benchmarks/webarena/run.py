#!/usr/bin/env python3
"""
benchmarks/webarena/run.py — Run WebArena evaluation on CWF.

Starts evaluation against self-hosted Docker web services using a local
LLM inference server and headless Playwright Chromium.

Usage:
  python3 benchmarks/webarena/run.py                               # default: 70b model
  python3 benchmarks/webarena/run.py --model 70b --inference-cores 570
  python3 benchmarks/webarena/run.py --model 70b --collect-emon    # global steady-state EMON
  python3 benchmarks/webarena/run.py --model 70b --emon            # per-task EMON collection
  python3 benchmarks/webarena/run.py --start-idx 0 --end-idx 10   # subset
  python3 benchmarks/webarena/run.py --dry-run

Prerequisites:
  1. Run setup.py first: python3 benchmarks/webarena/setup.py
  2. Ollama running (auto-started by setup.py) or llama-server on --llm-port
  3. For EMON: /opt/intel/sep installed + insmod drivers

Arguments:
  --model            8b | 32b | 70b                          default: 70b
  --ollama-model     Override exact Ollama model name        default: auto from --model
  --inference-cores  Cores for LLM                           default: auto
  --env-cores        Cores for Playwright + services         default: auto
  --start-idx        First task index                        default: 0
  --end-idx          Last task index (exclusive)             default: 812
  --llm-port         API port (11434=Ollama, 8000=llama.cpp) default: 11434
  --run-id           Unique label                            default: auto
  --collect-emon     Global steady-state EMON: 180s warmup + 300s collection, then
                     EDP post-processing (Excel/CSV output). Disables RAPL.
  --collect-rapl     Enable RAPL power monitoring            default: off
  --collect-temp     Enable temperature monitoring
  --emon             Collect EMON per task (start 2s after [Intent], stop at [Result])
  --dry-run          Print config, do not run

EMON modes (independent, can be combined):
  --collect-emon   Global: waits 3 min for steady state, collects 5 min, generates Excel
  --emon           Per-task: start/stop EMON around each individual task
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
from typing import Optional

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
from common.system_metadata import get_system_metadata, get_ollama_metadata
from common.csv_writer import write_csv_row
from common.json_results import ResultsJsonWriter
from common.telemetry import TelemetryManager
from common.telemetry.emon import EmonCollector
from common.cli_utils import setup_tee_logging, teardown_logging
from benchmarks.webarena.lib.ollama_metrics import OllamaMetricsProxy

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
    p.add_argument("--model",           default="70b",
                    help="Model shortcut: 8b | 32b | 70b (maps to llama3.1:<size>). "
                         "70b is the CWF sweet spot: 405b times out on CPU, 8b is too weak.")
    p.add_argument("--ollama-model",    default="", metavar="NAME",
                    help="Override the Ollama model name (e.g. 'llama3.1:70b'). "
                         "If empty, auto-maps from --model (llama3:8b / 32b / 70b).")
    # Default cores: auto-scale to platform total leaving 32 for OS+Playwright.
    # Falls back to 96 if CPUInfo is unavailable.
    try:
        _total_cores = CPUInfo().get_total_cores()
        _default_inf_cores = max(96, _total_cores - 32)
        _default_env_cores = 32
    except Exception:
        _default_inf_cores = 96
        _default_env_cores = 48
    p.add_argument("--inference-cores", type=int, default=_default_inf_cores)
    p.add_argument("--env-cores",       type=int, default=_default_env_cores)
    p.add_argument("--start-idx",       type=int, default=0)
    p.add_argument("--end-idx",         type=int, default=812)
    p.add_argument("--llm-port",        type=int, default=11434,
                    help="LLM API port (11434=Ollama, 8000=llama.cpp)")
    p.add_argument("--run-id",          default="")
    p.add_argument("--emon",            action="store_true",
                    help="Collect a separate EMON file per task (start 2s after [Intent], stop at [Result]). "
                         "Saves to telemetry/task_N/emon_task_N.txt. Requires /opt/intel/sep.")
    p.add_argument("--collect-emon",    action="store_true",
                    help="Global steady-state EMON: wait 180s warmup after workload starts, "
                         "collect for 300s, then post-process with EDP to generate Excel/CSV. "
                         "Disables RAPL (EMON captures power counters). Requires /opt/intel/sep.")
    p.add_argument("--collect-rapl",    action="store_true", default=False,
                    help="Enable RAPL power monitoring. Off by default when --collect-emon is used "
                         "(EMON already captures power counters).")
    p.add_argument("--collect-temp",    action="store_true")
    p.add_argument("--dry-run",         action="store_true")
    return p.parse_args()


_MODEL_MAP = {"8b": "llama3.1:8b", "32b": "llama3.1:32b", "70b": "llama3.1:70b"}


def _resolve_model_name(args: argparse.Namespace) -> str:
    """Return the final model name to pass to Ollama/OpenAI-compat API."""
    if args.ollama_model:
        return args.ollama_model
    return _MODEL_MAP.get(args.model, args.model)


def _ensure_webarena_patched() -> None:
    """Apply all CWF patches to the WebArena clone — idempotent, safe to call every run."""
    import re as _re

    if not WORKDIR.exists():
        return

    # Patch 1: tokenizers.py — overwrite entirely with a deterministic, known-good version.
    # Upstream raises KeyError on non-OpenAI model names (e.g. llama3.1:405b). Rather
    # than fragile in-place regex patching, we replace the whole file so the result
    # is always syntactically valid and idempotent across re-runs / partial states.
    _tf = WORKDIR / "llms" / "tokenizers.py"
    _good = (
        "from typing import Any\n"
        "\n"
        "import tiktoken\n"
        "from transformers import LlamaTokenizer  # type: ignore\n"
        "\n"
        "\n"
        "class Tokenizer(object):\n"
        "    def __init__(self, provider: str, model_name: str) -> None:\n"
        "        if provider == \"openai\":\n"
        "            try:\n"
        "                self.tokenizer = tiktoken.encoding_for_model(model_name)\n"
        "            except KeyError:\n"
        "                # CWF: non-OpenAI model name (e.g. llama3.1:405b). Fallback.\n"
        "                self.tokenizer = tiktoken.get_encoding(\"cl100k_base\")\n"
        "        elif provider == \"huggingface\":\n"
        "            self.tokenizer = LlamaTokenizer.from_pretrained(model_name)\n"
        "            # turn off adding special tokens automatically\n"
        "            self.tokenizer.add_special_tokens = False  # type: ignore[attr-defined]\n"
        "            self.tokenizer.add_bos_token = False  # type: ignore[attr-defined]\n"
        "            self.tokenizer.add_eos_token = False  # type: ignore[attr-defined]\n"
        "        else:\n"
        "            raise NotImplementedError\n"
        "\n"
        "    def encode(self, text: str) -> list[int]:\n"
        "        return self.tokenizer.encode(text)\n"
        "\n"
        "    def decode(self, ids: list[int]) -> str:\n"
        "        return self.tokenizer.decode(ids)\n"
        "\n"
        "    def __call__(self, text: str) -> list[int]:\n"
        "        return self.tokenizer.encode(text)\n"
    )
    if _tf.parent.exists():
        _tf.parent.mkdir(parents=True, exist_ok=True)
        if not _tf.exists() or _tf.read_text() != _good:
            _tf.write_text(_good)
            print("[webarena] Wrote deterministic tokenizers.py")

    # Patch 2: run.py — ZeroDivisionError when scores list is empty
    _rf = WORKDIR / "run.py"
    if _rf.exists():
        _c = _rf.read_text()
        _old = 'logger.info(f"Average score: {sum(scores) / len(scores)}")'
        _new = 'logger.info(f"Average score: {sum(scores) / len(scores) if scores else 0.0}")'
        if _old in _c:
            _rf.write_text(_c.replace(_old, _new))
            print("[webarena] Patched run.py: ZeroDivisionError guard")

    # Patch 3: helper_functions.py — hardcoded gpt-4-1106-preview evaluator
    _hf = WORKDIR / "evaluation_harness" / "helper_functions.py"
    if _hf.exists():
        _c = _hf.read_text()
        _p = _re.sub(
            r'model="gpt-4-1106-preview"',
            'model=__import__("os").environ.get("WEBARENA_EVAL_MODEL","gpt-4-1106-preview")',
            _c,
        )
        if _p != _c:
            _hf.write_text(_p)
            print("[webarena] Patched helper_functions.py: evaluator uses WEBARENA_EVAL_MODEL")

    # Patch 4: auto_login.py — 30s default timeout too short for slow Magento admin.
    # Increase ALL Playwright page timeouts to 90s. There are two new_page() calls
    # (is_expired + renew_comb) — replace ALL of them so both functions get 90s.
    _al = WORKDIR / "browser_env" / "auto_login.py"
    if _al.exists():
        _c = _al.read_text()
        _old_line = "    page = context.new_page()"
        _new_line = ("    page = context.new_page()\n"
                     "    page.set_default_timeout(90000)  # CWF: Magento admin is slow on bare-metal")
        if _old_line in _c and "set_default_timeout" not in _c:
            # Replace ALL occurrences (both is_expired and renew_comb functions)
            _al.write_text(_c.replace(_old_line, _new_line))
            print("[webarena] Patched auto_login.py: Playwright timeout 30s → 90s (all page contexts)")

    # Patch 5: openai_utils.py — default 600s OpenAI request_timeout is too short for
    # CPU-only inference of large models (e.g. llama3.1:405b). Inject request_timeout
    # from WEBARENA_REQUEST_TIMEOUT env var (default 7200s = 2h) into all create() calls.
    _ou = WORKDIR / "llms" / "providers" / "openai_utils.py"
    if _ou.exists():
        _c = _ou.read_text()
        if "request_timeout=" not in _c:
            _to = (
                'request_timeout=int(__import__("os").environ.get("WEBARENA_REQUEST_TIMEOUT", "7200"))'
            )
            # openai.ChatCompletion.create / .acreate and openai.Completion.create / .acreate
            _patched = _re.sub(
                r'(openai\.(?:Chat)?Completion\.a?create\(\s*#\s*type:\s*ignore)',
                rf'\1\n            {_to},',
                _c,
            )
            if _patched == _c:
                # Fallback: match without the trailing comment
                _patched = _re.sub(
                    r'(openai\.(?:Chat)?Completion\.a?create\()',
                    rf'\1\n            {_to},',
                    _c,
                )
            if _patched != _c:
                _ou.write_text(_patched)
                print("[webarena] Patched openai_utils.py: request_timeout via WEBARENA_REQUEST_TIMEOUT")


def _preflight_emon() -> None:
    """Print EMON availability diagnostic; does not abort."""
    sep_vars = Path("/opt/intel/sep/sep_vars.sh")
    if not sep_vars.exists():
        print("[WARN] EMON: /opt/intel/sep/sep_vars.sh not found — EMON disabled.\n"
              "  Fix: install SEP 5.58 beta to /opt/intel/sep", file=sys.stderr)
        return
    check = subprocess.run(
        f"source {sep_vars} && emon -version",
        shell=True, executable="/bin/bash", capture_output=True, text=True,
    )
    if check.returncode != 0:
        print("[WARN] EMON binary found but not working — drivers may not be loaded.\n"
              "  Fix: source /opt/intel/sep/sep_vars.sh && /opt/intel/sep/insmod-sep",
              file=sys.stderr)
    else:
        print(f"[INFO] EMON ready: {check.stdout.strip().splitlines()[0]}")


def _ensure_magento_configured() -> None:
    """Re-apply critical Magento settings every run — idempotent.

    Fixes: auto_login timeout because the admin login page never loads.
    Root cause: Magento has wrong base_url from the original image, or
    password-reset requirement is active, causing a redirect away from the
    login form.  Running these commands takes ~5s and is safe to repeat.
    """
    import shutil as _shutil

    if not _shutil.which("docker"):
        return

    # Check shopping_admin container is running
    check = subprocess.run(
        ["docker", "inspect", "--format={{.State.Running}}", "shopping_admin"],
        capture_output=True, text=True,
    )
    if check.returncode != 0 or check.stdout.strip() != "true":
        print("[WARN] shopping_admin container not running — skipping Magento config",
              file=sys.stderr)
        return

    # Read host IP from env file (same value used by Magento base_url)
    host = "localhost"
    env_file = Path.home() / ".cwf_webarena_env"
    if env_file.exists():
        import re as _re
        m = _re.search(r'SHOPPING_ADMIN="http://([^:]+):', env_file.read_text())
        if m:
            host = m.group(1)

    print(f"[webarena] Ensuring Magento admin configured for host={host} …")

    cmds = [
        # Base URLs
        f'/var/www/magento2/bin/magento setup:store-config:set --base-url="http://{host}:7780"',
        f'mysql -h 127.0.0.1 -u magentouser -pMyPassword magentodb '
        f'-e "UPDATE core_config_data SET value=\'http://{host}:7780/\' '
        f'WHERE path=\'web/secure/base_url\';"',
        # Disable forced password reset and password lifetime
        '/var/www/magento2/bin/magento config:set admin/security/password_is_forced 0',
        '/var/www/magento2/bin/magento config:set admin/security/password_lifetime 0',
        # Flush cache so settings take effect
        '/var/www/magento2/bin/magento cache:flush',
    ]
    for cmd in cmds:
        subprocess.run(
            f"docker exec shopping_admin {cmd}",
            shell=True, capture_output=True,
        )
    print("[webarena] Magento admin configured")


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
    # Use actual resolved model name so the run ID reflects the real model.
    # Sanitize colons and slashes (e.g. "llama3.1:405b" → "llama3.1-405b").
    model_key = _resolve_model_name(args).replace(":", "-").replace("/", "-")
    return f"webarena_{model_key}_{args.inference_cores}c_{n}tasks_{ts}"


def _run_with_per_task_emon(
    cmd: list,
    cwd: str,
    env: dict,
    out_dir: Path,
    sep_dir: str = "/opt/intel/sep",
    start_delay_s: float = 2.0,
) -> int:
    """Run the WebArena evaluation subprocess and collect a separate EMON file
    per task.

    Watches the streamed output for the three key log patterns emitted by
    WebArena's run.py:

        [Config file]: /tmp/.../N.json          → task index N (task is starting)
        [Intent]: ...                            → 2 s later: start emon -collect-edp
        [Result] ...  OR  [Unhandled Error] ...  → stop emon -stop immediately

    Each task's raw EMON data is saved to:
        <out_dir>/telemetry/task_<N>/emon_task_<N>.txt

    Returns the subprocess exit code.
    """
    import re
    import threading

    _current_emon: list = [None]   # EmonCollector in flight
    _pending_timer: list = [None]  # threading.Timer for delayed start (cancelable)
    _task_idx: list = [None]
    _edp_threads: list = []        # background EDP post-processing threads

    TARGET_SAMPLES = 600  # process up to 600 samples from the center of each task's collection;
                           # if fewer than 600 were collected, process all of them

    def _cancel_timer() -> None:
        t = _pending_timer[0]
        if t is not None:
            t.cancel()
            _pending_timer[0] = None

    def _stop_and_process_emon() -> None:
        """Stop the current EMON collector and kick off EDP post-processing in background."""
        ec = _current_emon[0]
        if ec is None:
            return
        _current_emon[0] = None
        ec.stop_collection()

        # Fire EDP post-processing in a daemon thread so the next task is not blocked.
        # Uses target_samples=TARGET_SAMPLES: always processes exactly 180 samples
        # (or all samples if fewer than 180 were collected), centered in the collection.
        def _edp():
            print(f"[per-task-emon] Post-processing {ec.output_file} (target={TARGET_SAMPLES} samples)…")
            result = ec.process_emon_with_edp(target_samples=TARGET_SAMPLES)
            if result:
                print(f"[per-task-emon] EDP done → {result}")
            else:
                print(f"[per-task-emon] EDP failed for {ec.output_file}")

        t = threading.Thread(target=_edp, daemon=True)
        t.start()
        _edp_threads.append(t)

    def _start_emon(idx: int, task_dir: Path) -> None:
        """Called from timer thread: create a new collector and start EMON."""
        task_dir.mkdir(parents=True, exist_ok=True)
        ec = EmonCollector(sep_dir=sep_dir, output_dir=str(task_dir))
        if ec.start_collection(session_name=f"emon_task_{idx}", duration_s=None):
            _current_emon[0] = ec
        else:
            print(f"[per-task-emon] WARNING: EMON start failed for task {idx}")

    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()

            # ── [Config file]: /tmp/.../N.json ──────────────────────────────
            # Marks the very start of a new task. Cancel any pending start timer
            # and stop any in-progress EMON from the previous task (+ trigger EDP).
            m = re.search(r'\[Config file\].*?[/\\](\d+)\.json', line)
            if m:
                _cancel_timer()
                _stop_and_process_emon()
                _task_idx[0] = int(m.group(1))

            # ── [Intent]: ... ───────────────────────────────────────────────
            # Task has been parsed and the agent is about to act. Schedule EMON
            # start after start_delay_s to skip the model's first cold token.
            if "[Intent]:" in line and _task_idx[0] is not None:
                idx = _task_idx[0]
                task_dir = out_dir / "telemetry" / f"task_{idx}"
                print(f"[per-task-emon] Task {idx}: EMON starts in {start_delay_s:.0f}s → {task_dir / f'emon_task_{idx}.txt'}")
                t = threading.Timer(start_delay_s, _start_emon, args=(idx, task_dir))
                t.daemon = True
                _pending_timer[0] = t
                t.start()

            # ── [Result] / [Unhandled Error] ────────────────────────────────
            # Task finished (pass or fail). Stop EMON and start EDP post-processing.
            if "[Result]" in line or "[Unhandled Error]" in line:
                _cancel_timer()
                _stop_and_process_emon()

    finally:
        # Ensure cleanup if the subprocess exits unexpectedly.
        _cancel_timer()
        _stop_and_process_emon()
        # Wait for all background EDP post-processing threads before returning.
        pending = [t for t in _edp_threads if t.is_alive()]
        if pending:
            print(f"[per-task-emon] Waiting for {len(pending)} EDP post-processing job(s) to finish…")
            for t in pending:
                t.join()

    proc.wait()
    return proc.returncode


def run_evaluation(args: argparse.Namespace, run_id: str,
                   proxy_port: Optional[int] = None) -> dict:
    """Invoke WebArena run.py. Returns result dict."""
    # Always apply patches to the WebArena clone before running — idempotent.
    _ensure_webarena_patched()

    results_dir = WORKDIR / "results" / run_id
    results_dir.mkdir(parents=True, exist_ok=True)

    base_url = (
        f"http://localhost:{proxy_port}/v1"
        if proxy_port is not None
        else f"http://localhost:{args.llm_port}/v1"
    )

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
    # Point the evaluator's fuzzy/ua match to the local model instead of gpt-4
    env.setdefault("WEBARENA_EVAL_MODEL", model_name)
    # Long OpenAI client timeout for slow CPU-only inference of large models.
    # Used by the openai_utils.py patch (see _ensure_webarena_patched).
    env.setdefault("WEBARENA_REQUEST_TIMEOUT", "7200")
    # Suppress beartype PEP 585 deprecation warnings from gymnasium (noisy, not actionable)
    env["PYTHONWARNINGS"] = "ignore::DeprecationWarning"

    # CRITICAL: Bypass Intel corporate proxy for all WebArena local services.
    # Playwright (Chromium) picks up system proxy settings. The Intel proxy
    # blocks requests to internal IPs (10.x.x.x) with HTTP 403 "Access Denied".
    # We must unset all proxy vars and explicitly set NO_PROXY to cover all
    # local service IPs and ports used by WebArena containers.
    for _pvar in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(_pvar, None)
    _local_no_proxy = "localhost,127.0.0.1,0.0.0.0,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    env["NO_PROXY"]  = _local_no_proxy
    env["no_proxy"]  = _local_no_proxy
    # Chromium also respects these env vars for proxy bypass
    env["PLAYWRIGHT_NO_PROXY"] = _local_no_proxy

    # Ensure WebArena's internal subprocess calls (e.g. auto_login.py) use the
    # venv python — not the system python3 which lacks playwright.
    # Prepending the venv bin to PATH means `python3` resolves to the venv python.
    venv_bin = str(WEBARENA_VENV_PYTHON.parent)
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = str(WEBARENA_VENV_PYTHON.parent.parent)
    # WebArena's run.py calls auto_login.py via hardcoded "python" (not sys.executable).
    # Set PYTHONPATH so even the system python can import playwright from the venv.
    venv_site = str(next(
        (WEBARENA_VENV_PYTHON.parent.parent / "lib").glob("python3*/site-packages"),
        WEBARENA_VENV_PYTHON.parent.parent / "lib" / "python3.11" / "site-packages",
    ))
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = venv_site + (os.pathsep + existing_pypath if existing_pypath else "")

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

    total_cpus = os.cpu_count() or 1
    if args.inference_cores < 0 or args.env_cores < 0:
        print("[ERROR] --inference-cores and --env-cores must be >= 0", file=sys.stderr)
        sys.exit(1)
    if args.inference_cores + args.env_cores > total_cpus:
        print(
            "[ERROR] Invalid core split: "
            f"inference_cores({args.inference_cores}) + env_cores({args.env_cores}) "
            f"> total_cpus({total_cpus}).\n"
            "  Hint: if you want to dedicate all CPUs to LLM, set --env-cores 0.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.dry_run:
        print("[dry-run] Would run:")
        print(f"  source {env_file}")
        if args.env_cores > 0:
            print(f"  taskset -c {args.inference_cores}-{args.inference_cores+args.env_cores-1} \\")
            print(f"    {' '.join(eval_cmd)}")
        else:
            print(f"  {' '.join(eval_cmd)}")
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

    run_rc: int
    if args.emon:
        run_rc = _run_with_per_task_emon(
            cmd=cmd,
            cwd=str(WORKDIR),
            env=env,
            out_dir=results_dir.parent,  # results/{run_id}/
            sep_dir="/opt/intel/sep",
        )
    else:
        run_rc = subprocess.run(cmd, cwd=str(WORKDIR), env=env).returncode
    if run_rc != 0:
        print(f"[ERROR] WebArena evaluation command failed with exit code {run_rc}", file=sys.stderr)
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
        if args.emon or args.collect_emon:
            _preflight_emon()
        _ensure_magento_configured()

    # TeeOutput: mirror all stdout/stderr to console_output.log (pnpwls pattern)
    if not args.dry_run:
        setup_tee_logging(out_dir / "console_output.log")

    # ── Inference metrics proxy ───────────────────────────────────────────────
    # Start OllamaMetricsProxy on llm_port+1 so WebArena's LLM calls are
    # intercepted and translated to Ollama's native /api/chat endpoint,
    # which includes full per-request timing (eval_count, eval_duration, etc.).
    proxy_port: Optional[int] = None
    _proxy: Optional[OllamaMetricsProxy] = None
    if not args.dry_run:
        _candidate_port = args.llm_port + 1
        _proxy = OllamaMetricsProxy(
            ollama_port=args.llm_port,
            proxy_port=_candidate_port,
        )
        if _proxy.start():
            proxy_port = _candidate_port
            print(f"[ollama-proxy] Metrics proxy started on port {proxy_port} "
                  f"(forwarding → localhost:{args.llm_port})")
        else:
            _proxy = None

    try:
        cpu = CPUInfo()
        os_info = OSInfo()
        platform = detect_platform()
        model_label = _resolve_model_name(args)

        print(f"\n{'='*60}")
        print("  WebArena Runner")
        print(f"  Run ID    : {run_id}")
        print(f"  Platform  : {platform}")
        print(f"  Model     : {model_label}  Inf-cores: {args.inference_cores}")
        print(f"  Tasks     : {args.start_idx}..{args.end_idx}")
        print(f"  Output    : {out_dir}")
        if args.emon:
            print("  EMON      : per-task mode (start +2s after [Intent], stop at [Result])")
        if args.collect_emon:
            print("  EMON      : global steady-state (180s warmup → 300s collection → EDP)")
        print(f"{'='*60}\n")

        sys_meta = get_system_metadata(cpu, os_info, run_id=run_id,
                                       experiment_name=BENCHMARK)

        # ── Collect and write system_metadata.json ────────────────────────────
        ollama_meta = get_ollama_metadata(port=args.llm_port)
        full_meta = dict(sys_meta)
        full_meta.update(ollama_meta)
        full_meta["inference_cores"] = str(args.inference_cores)
        full_meta["env_cores"]       = str(args.env_cores)
        full_meta["llm_model"]       = model_label
        full_meta["llm_port"]        = str(args.llm_port)
        try:
            (out_dir / "system_metadata.json").write_text(
                json.dumps(full_meta, indent=2)
            )
        except Exception as _e:
            print(f"[WARN] Could not write system_metadata.json: {_e}", file=sys.stderr)

        # Warn early if EMON window may not be fully covered
        if args.collect_emon and not args.dry_run:
            n_tasks = args.end_idx - args.start_idx
            if n_tasks == 0:
                print(
                    "[WARN] --collect-emon with 0 tasks: EMON will start but workload "
                    "finishes immediately before the 300s collection window completes.",
                    file=sys.stderr,
                )

        # When --collect-emon is active, EMON captures power counters so RAPL is
        # redundant.  Allow explicit --collect-rapl to override this for edge cases.
        collect_rapl_effective = args.collect_rapl and not args.collect_emon

        # --emon manages its own per-task EmonCollector instances; global EMON is
        # controlled by --collect-emon.
        tm = TelemetryManager(
            output_dir=str(out_dir / "telemetry"),
            platform=platform,
            collect_emon=args.collect_emon,
            collect_rapl=collect_rapl_effective,
            collect_temp=args.collect_temp,
            emon_warmup_s=180 if args.collect_emon else 0,
            emon_duration_s=300 if args.collect_emon else None,
        )
        _TELEMETRY_MANAGER = tm

        if not args.dry_run:
            tm.start(session_name=run_id)

        bench_results = run_evaluation(args, run_id, proxy_port=proxy_port)

        if not args.dry_run:
            print("\n[telemetry] Stopping collectors and processing EMON...")
            tm.stop(process_emon=args.collect_emon, sockets=cpu.get_sockets())
            print("[telemetry] Collection complete.")

        # ── Collect inference metrics from proxy ──────────────────────────────
        infer_metrics: dict = {}
        if _proxy is not None:
            infer_metrics = _proxy.get_aggregate_metrics()
            per_req = _proxy.get_per_request_metrics()
            # Write per-request detail to inference_metrics.json
            try:
                (out_dir / "inference_metrics.json").write_text(
                    json.dumps({"aggregate": infer_metrics, "per_request": per_req}, indent=2)
                )
            except Exception as _e:
                print(f"[WARN] Could not write inference_metrics.json: {_e}", file=sys.stderr)

        common_data: OrderedDict = OrderedDict()
        common_data.update(bench_results)
        common_data.update(sys_meta)
        common_data["pkg_power_w"]  = str(tm.pkg_power_w)
        common_data["dram_power_w"] = str(tm.dram_power_w)
        # Inference metrics (N/A strings when proxy was not used)
        common_data["avg_prompt_eval_tok_s"]   = str(infer_metrics.get("avg_prompt_eval_tok_s",   "N/A"))
        common_data["avg_generation_tok_s"]    = str(infer_metrics.get("avg_generation_tok_s",    "N/A"))
        common_data["avg_ttft_ms"]             = str(infer_metrics.get("avg_ttft_ms",             "N/A"))
        common_data["total_prompt_tokens"]     = str(infer_metrics.get("total_prompt_tokens",     0))
        common_data["total_completion_tokens"] = str(infer_metrics.get("total_completion_tokens", 0))
        common_data["total_inference_time_s"]  = str(infer_metrics.get("total_inference_time_s",  0.0))
        common_data["num_llm_requests"]        = str(infer_metrics.get("num_llm_requests",        0))
        # Ollama metadata
        common_data["ollama_version"]          = ollama_meta.get("ollama_version",      "N/A")
        common_data["ollama_model_name"]       = ollama_meta.get("ollama_model_name",   "N/A")
        common_data["ollama_model_size_gb"]    = ollama_meta.get("ollama_model_size_gb","N/A")
        common_data["ollama_quantization"]     = ollama_meta.get("ollama_quantization", "N/A")
        common_data["ollama_num_threads"]      = ollama_meta.get("ollama_num_threads",  "N/A")
        # EMON telemetry status (for --collect-emon global mode)
        common_data["emon_collected"]          = str(tm.emon_ready)
        common_data["emon_output_dir"]         = str(tm.emon_output_dir) if tm.emon_output_dir else "N/A"

        write_csv_row(out_dir / "results.csv",
                      list(common_data.keys()), list(common_data.values()))
        rw = ResultsJsonWriter(output_dir=out_dir, run_id=run_id)
        rw.add_row(common_data=common_data, rapl_data=tm.rapl_mean)
        rw.save()

        # ── Final Summary ─────────────────────────────────────────────────────
        total_tokens = (infer_metrics.get("total_prompt_tokens", 0)
                        + infer_metrics.get("total_completion_tokens", 0))
        total_runtime_s = float(bench_results.get("total_runtime_s") or 0)
        pkg_w = tm.pkg_power_w
        dram_w = tm.dram_power_w
        total_infer_s = infer_metrics.get("total_inference_time_s", 0) or 0

        # Energy per token (J/token) = package_power_W * inference_time_s / total_tokens.
        # Note: pkg_w is mean power over the entire run (RAPL), so this is a
        # conservative upper bound — actual inference-only energy will be lower.
        # total_infer_s is guaranteed numeric (0.0 when proxy is unavailable).
        energy_per_tok = "N/A"
        if total_infer_s > 0 and total_tokens > 0 and pkg_w > 0:
            energy_per_tok = f"{(pkg_w * total_infer_s) / total_tokens:.2f}"

        print(f"\n{'='*70}")
        print("  WebArena Run Summary")
        print(f"{'='*70}")
        print(f"  Run ID           : {run_id}")
        print(f"  Platform         : {platform}")
        total_cores = sys_meta.get("total_cores", "N/A")
        numa_nodes  = sys_meta.get("numa_nodes",  "N/A")
        print(f"  CPU              : {sys_meta.get('cpu_model', 'N/A')} "
              f"{total_cores} cores / {numa_nodes} NUMA nodes")
        mem_gb = sys_meta.get("memory_total_gb", "N/A")
        print(f"  RAM              : {mem_gb} GB")
        quant    = ollama_meta.get("ollama_quantization", "N/A")
        size_gb  = ollama_meta.get("ollama_model_size_gb","N/A")
        print(f"  Model            : {model_label} ({quant}, {size_gb}GB)")
        print()
        print(f"  Tasks Completed  : {bench_results.get('tasks_completed', 'N/A')}/{bench_results.get('n_tasks', 'N/A')}")
        print(f"  Success Rate     : {bench_results.get('success_rate', 'N/A')}%")
        print(f"  Total Runtime    : {bench_results.get('total_runtime_s', 'N/A')}s")
        if infer_metrics:
            avg_pe  = infer_metrics.get("avg_prompt_eval_tok_s", "N/A")
            avg_gen = infer_metrics.get("avg_generation_tok_s",  "N/A")
            avg_tt  = infer_metrics.get("avg_ttft_ms",           "N/A")
            pt      = infer_metrics.get("total_prompt_tokens",     0)
            ct      = infer_metrics.get("total_completion_tokens", 0)
            num_req = infer_metrics.get("num_llm_requests",        0)
            print("\n  Inference Metrics:")
            print(f"    Prompt Eval    : {avg_pe} tok/s (avg across {num_req} requests)")
            print(f"    Generation     : {avg_gen} tok/s (avg)")
            if isinstance(avg_tt, (int, float)):
                # avg_ttft_ms is stored in milliseconds; display in seconds for readability.
                # isinstance guard needed because _avg() returns "N/A" (str) when no requests were recorded.
                print(f"    TTFT           : {avg_tt/1000:.2f}s (avg)")
            else:
                print(f"    TTFT           : {avg_tt}")
            print(f"    Total Tokens   : {total_tokens:,} (prompt: {pt:,} + completion: {ct:,})")
            print(f"    Inference Time : {total_infer_s}s (of {total_runtime_s:.1f}s total)")
        if args.collect_emon:
            # Global steady-state EMON was active — show EDP output status.
            _emon_has_file = (
                tm.emon is not None
                and tm.emon.output_file is not None
                and tm.emon.output_file.exists()
            )
            _emon_status = "Collected + Processed" if tm.emon_ready else (
                "Collected (EDP processing failed)" if _emon_has_file
                else "Not collected (EMON unavailable)"
            )
            _emon_out = str(tm.emon_output_dir) if tm.emon_output_dir else "N/A"
            print("\n  EMON Telemetry:")
            print(f"    Status         : {_emon_status}")
            print(f"    Collection     : 300s steady-state (after 180s warmup)")
            print(f"    Samples        : ~40 (7.5s per sample on CWF)")
            print(f"    Output         : {_emon_out}")
            if tm.emon_ready and tm.emon_output_dir:
                _xlsx = list(Path(tm.emon_output_dir).glob("*socket_view*summary*.xlsx"))
                if _xlsx:
                    print(f"    Excel Files    : {', '.join(f.name for f in _xlsx[:3])}")
        if collect_rapl_effective:
            # RAPL was active (no --collect-emon, or explicit --collect-rapl override).
            print("\n  Power Metrics (RAPL):")
            print(f"    Package Power  : {pkg_w:.1f}W (mean)")
            print(f"    DRAM Power     : {dram_w:.1f}W (mean)")
            if energy_per_tok != "N/A":
                print(f"    Energy/Token   : {energy_per_tok} J/token")
        if args.emon:
            task_dirs = sorted((out_dir / "telemetry").glob("task_*")) if (out_dir / "telemetry").exists() else []
            print(f"\n  Per-task EMON    : {len(task_dirs)} task(s) collected")
            for td in task_dirs[:5]:
                txt_files = list(td.glob("*.txt"))
                status = f"{txt_files[0].name} ({txt_files[0].stat().st_size // 1024}KB)" if txt_files else "empty"
                print(f"    {td.name}: {status}")
            if len(task_dirs) > 5:
                print(f"    ... and {len(task_dirs)-5} more")
        print(f"\n  Results Location : {out_dir}")
        print(f"{'='*70}\n")

    except KeyboardInterrupt:
        print("\n\n[webarena] Interrupted by user.")
    except Exception as exc:
        print(f"\n[webarena] Fatal error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if _proxy is not None:
            _proxy.stop()
        teardown_logging()


if __name__ == "__main__":
    main()
