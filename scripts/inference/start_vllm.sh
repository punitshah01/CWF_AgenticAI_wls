#!/usr/bin/env bash
# =============================================================================
# start_vllm.sh — CWF Agentic AI: vLLM Inference Server
# Optimized for Clearwater Forest (CWF) E-core Darkmont, no SMT
# Backend: CPU (OpenVINO auto-detected) or PyTorch CPU
# API: OpenAI-compatible endpoint on :8000
# =============================================================================
set -euo pipefail

# ── Defaults (override via CLI or environment) ────────────────────────────────
MODEL_SIZE="${MODEL_SIZE:-8b}"          # 8b | 32b | 70b
INFERENCE_CORES="${INFERENCE_CORES:-64}" # Cores to pin LLM to
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
DTYPE="${DTYPE:-auto}"                  # auto | float32 | bfloat16
QUANTIZATION="${QUANTIZATION:-}"        # empty | awq | gptq | squeezellm

# ── CLI args ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)   MODEL_SIZE="$2";       shift 2 ;;
        --cores)   INFERENCE_CORES="$2";  shift 2 ;;
        --port)    PORT="$2";             shift 2 ;;
        --ctx)     MAX_MODEL_LEN="$2";    shift 2 ;;
        --quant)   QUANTIZATION="$2";     shift 2 ;;
        *) echo "[WARN] Unknown arg: $1"; shift ;;
    esac
done

# ── Model selection ───────────────────────────────────────────────────────────
case "$MODEL_SIZE" in
    8b)
        MODEL_ID="meta-llama/Llama-3.1-8B-Instruct"
        ;;
    32b | coder-32b)
        MODEL_ID="Qwen/Qwen2.5-Coder-32B-Instruct"
        ;;
    32b-qwen)
        MODEL_ID="Qwen/Qwen2.5-32B-Instruct"
        ;;
    70b)
        MODEL_ID="meta-llama/Llama-3.1-70B-Instruct"
        ;;
    *)
        MODEL_ID="$MODEL_SIZE"  # allow full HF path
        ;;
esac

# ── System info ───────────────────────────────────────────────────────────────
TOTAL_CORES=$(nproc --all)
echo "============================================="
echo "CWF vLLM Inference Server"
echo "Model     : $MODEL_ID"
echo "Cores     : $INFERENCE_CORES / $TOTAL_CORES (pinned via numactl)"
echo "Port      : $PORT"
echo "Max ctx   : $MAX_MODEL_LEN"
echo "Dtype     : $DTYPE"
echo "Quant     : ${QUANTIZATION:-none}"
echo "============================================="

# ── Validate vllm is installed ────────────────────────────────────────────────
if ! command -v vllm &>/dev/null; then
    echo "[ERROR] vllm not found. Install with: pip install vllm"
    exit 1
fi
echo "[OK] vllm $(pip show vllm | grep Version | awk '{print $2}')"

# ── Build command ─────────────────────────────────────────────────────────────
# CWF note: --device cpu uses OpenVINO backend when available (auto-detected).
# --tensor-parallel-size 1: no GPU tensor parallel on CPU.
# OMP_NUM_THREADS: limits PyTorch/OpenVINO to pinned cores.
# KMP_BLOCKTIME=1: reduces OpenMP idle spin for bursty inference.

VLLM_ARGS=(
    serve "$MODEL_ID"
    --device cpu
    --dtype "$DTYPE"
    --tensor-parallel-size 1
    --port "$PORT"
    --max-model-len "$MAX_MODEL_LEN"
    --cpu-offload-gb 0
    --served-model-name "local-llm"
    --disable-log-requests
)

# Optional quantization
if [ -n "$QUANTIZATION" ]; then
    VLLM_ARGS+=(--quantization "$QUANTIZATION")
fi

# ── Core pinning via numactl ──────────────────────────────────────────────────
# CWF: single NUMA domain in most configs; use CPU list for fine-grained binding.
# Inference cores: 0 to (INFERENCE_CORES-1)
CPU_LIST="0-$((INFERENCE_CORES - 1))"
echo "[INFO] Pinning to CPUs: $CPU_LIST"
echo "[INFO] OMP_NUM_THREADS=$INFERENCE_CORES"

export OMP_NUM_THREADS="$INFERENCE_CORES"
export KMP_BLOCKTIME=1
export KMP_AFFINITY="granularity=fine,compact,1,0"
export GOMP_SPINCOUNT=0
# Disable OpenVINO telemetry
export OV_TELEMETRY_OPTOUT=1

echo ""
echo "--- Starting vLLM server (Ctrl+C to stop) ---"
echo "Command: numactl --physcpubind=$CPU_LIST vllm ${VLLM_ARGS[*]}"
echo ""

exec numactl --physcpubind="$CPU_LIST" \
    vllm "${VLLM_ARGS[@]}"
