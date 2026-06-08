#!/usr/bin/env python3
"""
scripts/inference/start_vllm.py — CWF vLLM Inference Server
=============================================================
Starts a vLLM OpenAI-compatible API server pinned to a specific CPU core range.
Optimized for Clearwater Forest (CWF) E-core Darkmont, no SMT.

Backend: --device cpu uses OpenVINO when available (auto-detected by vLLM).
API:     OpenAI-compatible at http://localhost:<port>/v1

Usage:
  python3 scripts/inference/start_vllm.py                 # defaults: 8b model, 64 cores, port 8000
  python3 scripts/inference/start_vllm.py --model 32b --cores 96
  python3 scripts/inference/start_vllm.py --model Qwen/Qwen2.5-Coder-32B-Instruct --cores 128
  python3 scripts/inference/start_vllm.py --model 8b --port 8001 --quant awq

Model shortcuts:
  8b          → meta-llama/Llama-3.1-8B-Instruct
  32b         → Qwen/Qwen2.5-Coder-32B-Instruct
  32b-qwen    → Qwen/Qwen2.5-32B-Instruct
  70b         → meta-llama/Llama-3.1-70B-Instruct
  <any string> treated as a full HuggingFace model ID
"""

import argparse
import os
import shutil
import subprocess
import sys

# ── Model ID map ──────────────────────────────────────────────────────────────
MODEL_MAP = {
    "8b":        "meta-llama/Llama-3.1-8B-Instruct",
    "32b":       "Qwen/Qwen2.5-Coder-32B-Instruct",
    "coder-32b": "Qwen/Qwen2.5-Coder-32B-Instruct",
    "32b-qwen":  "Qwen/Qwen2.5-32B-Instruct",
    "70b":       "meta-llama/Llama-3.1-70B-Instruct",
}


def get_total_cores() -> int:
    try:
        result = subprocess.run(["nproc", "--all"], capture_output=True, text=True)
        return int(result.stdout.strip())
    except Exception:
        return os.cpu_count() or 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CWF vLLM Inference Server (OpenAI-compatible)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", default="8b",
                        help="Model size shortcut or full HF model ID. "
                             "Shortcuts: 8b, 32b, 32b-qwen, 70b. Default: 8b")
    parser.add_argument("--cores", type=int, default=64,
                        help="Number of cores to pin LLM to (CPUs 0 to N-1). Default: 64")
    parser.add_argument("--port", type=int, default=8000,
                        help="API server port. Default: 8000")
    parser.add_argument("--ctx", type=int, default=8192,
                        help="Max model context length (tokens). Default: 8192")
    parser.add_argument("--dtype", default="auto",
                        help="Weight dtype: auto | float32 | bfloat16. Default: auto")
    parser.add_argument("--quant", default="",
                        help="Quantization method: awq | gptq | squeezellm (optional)")
    args = parser.parse_args()

    model_id = MODEL_MAP.get(args.model, args.model)
    total_cores = get_total_cores()
    cpu_list = f"0-{args.cores - 1}"

    # Validate
    if not shutil.which("vllm") and not shutil.which("python3"):
        print("[ERROR] vllm not found. Install with: pip install vllm", file=sys.stderr)
        sys.exit(1)

    print("=" * 50)
    print("  CWF vLLM Inference Server")
    print(f"  Model     : {model_id}")
    print(f"  Cores     : {args.cores} / {total_cores}  (pinned via numactl {cpu_list})")
    print(f"  Port      : {args.port}")
    print(f"  Max ctx   : {args.ctx}")
    print(f"  Dtype     : {args.dtype}")
    print(f"  Quant     : {args.quant or 'none'}")
    print("=" * 50)

    # Build vllm serve command
    vllm_cmd = [
        "vllm", "serve", model_id,
        "--device", "cpu",
        "--dtype", args.dtype,
        "--tensor-parallel-size", "1",
        "--port", str(args.port),
        "--max-model-len", str(args.ctx),
        "--cpu-offload-gb", "0",
        "--served-model-name", "local-llm",
        "--disable-log-requests",
    ]
    if args.quant:
        vllm_cmd += ["--quantization", args.quant]

    # Environment: core-pinned OpenMP settings for CWF E-core
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS":  str(args.cores),
        "KMP_BLOCKTIME":    "1",
        "KMP_AFFINITY":     "granularity=fine,compact,1,0",
        "GOMP_SPINCOUNT":   "0",
        "OV_TELEMETRY_OPTOUT": "1",        # disable OpenVINO telemetry
    })

    # Wrap with numactl for CPU pinning
    if shutil.which("numactl"):
        cmd = ["numactl", f"--physcpubind={cpu_list}"] + vllm_cmd
    else:
        print("[WARN] numactl not found — running without CPU pinning", file=sys.stderr)
        cmd = vllm_cmd

    print(f"\n[INFO] Pinning to CPUs: {cpu_list}")
    print(f"[INFO] OMP_NUM_THREADS={args.cores}")
    print("\n--- Starting vLLM server (Ctrl+C to stop) ---")
    print(f"Command: {' '.join(cmd)}\n")

    try:
        os.execvpe(cmd[0], cmd, env)   # replace process — no return
    except FileNotFoundError:
        # execvpe failed: vllm not in PATH, try via python -m
        print("[INFO] vllm binary not found, trying python -m vllm.entrypoints.openai.api_server",
              file=sys.stderr)
        vllm_cmd[0:2] = [sys.executable, "-m", "vllm.entrypoints.openai.api_server",
                         model_id]
        if shutil.which("numactl"):
            cmd = ["numactl", f"--physcpubind={cpu_list}"] + vllm_cmd
        else:
            cmd = vllm_cmd
        os.execvpe(cmd[0], cmd, env)


if __name__ == "__main__":
    main()
