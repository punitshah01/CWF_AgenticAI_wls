#!/usr/bin/env python3
"""
scripts/inference/start_llamacpp.py — CWF llama.cpp Inference Server
=====================================================================
Starts a llama.cpp server pinned to a specific CPU core range.
Optimized for Clearwater Forest (CWF) E-core Darkmont + AVX-VNNI.
Uses GGUF quantized models for best performance on CWF.

API: OpenAI-compatible at http://localhost:<port>/v1

Usage:
  python3 scripts/inference/start_llamacpp.py                  # defaults
  python3 scripts/inference/start_llamacpp.py --model 32b --cores 96
  python3 scripts/inference/start_llamacpp.py --model 8b --quant Q8_0
  python3 scripts/inference/start_llamacpp.py --model /path/to/model.gguf

Model shortcuts:
  8b          → llama-3.1-8b-instruct-<quant>.gguf
  32b         → qwen2.5-coder-32b-instruct-<quant>.gguf
  32b-qwen    → qwen2.5-32b-instruct-<quant>.gguf
  70b         → llama-3.1-70b-instruct-<quant>.gguf
  <path>      → used directly as model file path

Build llama.cpp with AVX-VNNI support (recommended for CWF):
  git clone https://github.com/ggerganov/llama.cpp
  cmake -B llama.cpp/build -DGGML_AVX_VNNI=ON -DGGML_AVX2=ON -DGGML_F16C=ON
  cmake --build llama.cpp/build --config Release -j$(nproc)
  sudo cp llama.cpp/build/bin/llama-server /usr/local/bin/
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Model file map ────────────────────────────────────────────────────────────
# Key → (filename_template, HuggingFace repo for auto-download hint)
MODEL_MAP = {
    "8b": (
        "llama-3.1-8b-instruct-{quant}.gguf",
        "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
    ),
    "32b": (
        "qwen2.5-coder-32b-instruct-{quant}.gguf",
        "bartowski/Qwen2.5-Coder-32B-Instruct-GGUF",
    ),
    "coder-32b": (
        "qwen2.5-coder-32b-instruct-{quant}.gguf",
        "bartowski/Qwen2.5-Coder-32B-Instruct-GGUF",
    ),
    "32b-qwen": (
        "qwen2.5-32b-instruct-{quant}.gguf",
        "bartowski/Qwen2.5-32B-Instruct-GGUF",
    ),
    "70b": (
        "llama-3.1-70b-instruct-{quant}.gguf",
        "bartowski/Meta-Llama-3.1-70B-Instruct-GGUF",
    ),
}


def get_total_cores() -> int:
    try:
        r = subprocess.run(["nproc", "--all"], capture_output=True, text=True)
        return int(r.stdout.strip())
    except Exception:
        return os.cpu_count() or 1


def find_llama_server() -> str:
    """Return path to llama-server binary, or empty string if not found."""
    for candidate in ("llama-server", "server"):
        path = shutil.which(candidate)
        if path:
            return path
    # Check common build locations
    for p in [Path("llama.cpp/build/bin/llama-server"),
              Path("/usr/local/bin/llama-server"),
              Path("./llama-server")]:
        if p.exists():
            return str(p)
    return ""


def resolve_model_file(model_arg: str, quant: str, models_dir: Path) -> tuple:
    """Resolve model file path and HF hint. Returns (path_str, hf_repo)."""
    if Path(model_arg).exists():
        return str(model_arg), ""

    entry = MODEL_MAP.get(model_arg)
    if entry:
        filename_tmpl, hf_repo = entry
        filename = filename_tmpl.format(quant=quant.lower())
        model_path = models_dir / filename
        return str(model_path), hf_repo

    # Treat as literal path
    return str(models_dir / model_arg), ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CWF llama.cpp Inference Server (OpenAI-compatible)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", default="8b",
                        help="Model shortcut (8b, 32b, 70b) or full path to .gguf. Default: 8b")
    parser.add_argument("--cores", type=int, default=64,
                        help="CPU threads for inference (CPUs 0 to N-1). Default: 64")
    parser.add_argument("--port", type=int, default=8000,
                        help="API server port. Default: 8000")
    parser.add_argument("--ctx", type=int, default=8192,
                        help="Context size (tokens). Default: 8192")
    parser.add_argument("--batch", type=int, default=512,
                        help="Batch size. Default: 512")
    parser.add_argument("--quant", default="Q4_K_M",
                        help="GGUF quant: Q4_K_M | Q8_0 | Q5_K_M | Q4_0. Default: Q4_K_M")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Parallel request slots. Default: 1")
    parser.add_argument("--models-dir", default=str(Path.home() / "models"),
                        help="Directory containing .gguf model files. Default: ~/models")
    args = parser.parse_args()

    total_cores = get_total_cores()
    models_dir = Path(args.models_dir)
    model_file, hf_repo = resolve_model_file(args.model, args.quant, models_dir)
    cpu_list = f"0-{args.cores - 1}"

    # Locate llama-server
    llama_server = find_llama_server()
    if not llama_server:
        print("[ERROR] llama-server not found in PATH.", file=sys.stderr)
        print("  Build from source with AVX-VNNI support:", file=sys.stderr)
        print("    git clone https://github.com/ggerganov/llama.cpp", file=sys.stderr)
        print("    cmake -B llama.cpp/build -DGGML_AVX_VNNI=ON -DGGML_AVX2=ON",
              file=sys.stderr)
        print("    cmake --build llama.cpp/build --config Release -j$(nproc)",
              file=sys.stderr)
        print("    sudo cp llama.cpp/build/bin/llama-server /usr/local/bin/",
              file=sys.stderr)
        sys.exit(1)

    # Check model file
    if not Path(model_file).exists():
        print(f"[WARN] Model file not found: {model_file}", file=sys.stderr)
        if hf_repo:
            print("  Download with huggingface-cli:", file=sys.stderr)
            print(f"    huggingface-cli download {hf_repo} \\", file=sys.stderr)
            print(f"      --include '*{args.quant.lower()}*.gguf' \\", file=sys.stderr)
            print(f"      --local-dir {models_dir}", file=sys.stderr)
        print("  Continuing — llama-server will error if the path is wrong.", file=sys.stderr)

    print("=" * 50)
    print("  CWF llama.cpp Inference Server")
    print(f"  Model     : {model_file}")
    print(f"  Quant     : {args.quant}")
    print(f"  Threads   : {args.cores} / {total_cores}")
    print(f"  Context   : {args.ctx}")
    print(f"  Batch     : {args.batch}")
    print(f"  Parallel  : {args.parallel} request slots")
    print(f"  Port      : {args.port}")
    print("=" * 50)

    # Build llama-server command
    server_cmd = [
        llama_server,
        "--model", model_file,
        "--threads", str(args.cores),
        "--ctx-size", str(args.ctx),
        "--batch-size", str(args.batch),
        "--parallel", str(args.parallel),
        "--port", str(args.port),
        "--host", "0.0.0.0",
    ]

    # Environment
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": str(args.cores),
        "KMP_BLOCKTIME":   "1",
    })

    # Wrap with numactl
    if shutil.which("numactl"):
        cmd = ["numactl", f"--physcpubind={cpu_list}"] + server_cmd
    else:
        print("[WARN] numactl not found — running without CPU pinning", file=sys.stderr)
        cmd = server_cmd

    print(f"\n[INFO] Pinning to CPUs: {cpu_list}")
    print(f"[INFO] OMP_NUM_THREADS={args.cores}")
    print("\n--- Starting llama.cpp server (Ctrl+C to stop) ---")
    print(f"Command: {' '.join(cmd)}\n")

    os.execvpe(cmd[0], cmd, env)   # replace process — no return


if __name__ == "__main__":
    main()
