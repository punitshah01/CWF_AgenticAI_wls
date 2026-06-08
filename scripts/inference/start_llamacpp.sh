#!/usr/bin/env bash
# =============================================================================
# start_llamacpp.sh — CWF Agentic AI: llama.cpp Inference Server
# Optimized for Clearwater Forest (CWF) E-core Darkmont + AVX-VNNI
# Format: GGUF with Q4_K_M quantization (recommended for CWF)
# API: OpenAI-compatible endpoint on :8000
# =============================================================================
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
MODEL_SIZE="${MODEL_SIZE:-8b}"
INFERENCE_CORES="${INFERENCE_CORES:-64}"
PORT="${PORT:-8000}"
CTX_SIZE="${CTX_SIZE:-8192}"
BATCH_SIZE="${BATCH_SIZE:-512}"
MODELS_DIR="${MODELS_DIR:-$HOME/models}"
QUANT="${QUANT:-Q4_K_M}"              # Q4_K_M | Q8_0 | Q4_0 | Q5_K_M
PARALLEL="${PARALLEL:-1}"             # parallel request slots

# ── CLI args ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)   MODEL_SIZE="$2";       shift 2 ;;
        --cores)   INFERENCE_CORES="$2";  shift 2 ;;
        --port)    PORT="$2";             shift 2 ;;
        --ctx)     CTX_SIZE="$2";         shift 2 ;;
        --batch)   BATCH_SIZE="$2";       shift 2 ;;
        --quant)   QUANT="$2";            shift 2 ;;
        --models-dir) MODELS_DIR="$2";    shift 2 ;;
        --parallel)   PARALLEL="$2";      shift 2 ;;
        *) echo "[WARN] Unknown arg: $1"; shift ;;
    esac
done

# ── Model file selection ──────────────────────────────────────────────────────
case "$MODEL_SIZE" in
    8b)
        MODEL_FILE="$MODELS_DIR/llama-3.1-8b-instruct-${QUANT,,}.gguf"
        HF_FALLBACK="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
        ;;
    32b | coder-32b)
        MODEL_FILE="$MODELS_DIR/qwen2.5-coder-32b-instruct-${QUANT,,}.gguf"
        HF_FALLBACK="bartowski/Qwen2.5-Coder-32B-Instruct-GGUF"
        ;;
    32b-qwen)
        MODEL_FILE="$MODELS_DIR/qwen2.5-32b-instruct-${QUANT,,}.gguf"
        HF_FALLBACK="bartowski/Qwen2.5-32B-Instruct-GGUF"
        ;;
    70b)
        MODEL_FILE="$MODELS_DIR/llama-3.1-70b-instruct-${QUANT,,}.gguf"
        HF_FALLBACK="bartowski/Meta-Llama-3.1-70B-Instruct-GGUF"
        ;;
    *)
        MODEL_FILE="$MODEL_SIZE"
        HF_FALLBACK=""
        ;;
esac

TOTAL_CORES=$(nproc --all)
echo "============================================="
echo "CWF llama.cpp Inference Server"
echo "Model     : $MODEL_FILE"
echo "Quant     : $QUANT"
echo "Threads   : $INFERENCE_CORES / $TOTAL_CORES"
echo "Context   : $CTX_SIZE"
echo "Batch     : $BATCH_SIZE"
echo "Parallel  : $PARALLEL request slots"
echo "Port      : $PORT"
echo "============================================="

# ── Validate llama-server binary ──────────────────────────────────────────────
LLAMA_SERVER=""
for bin in llama-server llama.cpp/server ./llama-server; do
    if command -v "$bin" &>/dev/null 2>&1; then
        LLAMA_SERVER="$bin"
        break
    fi
done

if [ -z "$LLAMA_SERVER" ]; then
    echo "[ERROR] llama-server not found in PATH."
    echo "  Build from source with AVX-VNNI support:"
    echo "    git clone https://github.com/ggerganov/llama.cpp"
    echo "    cd llama.cpp"
    echo "    cmake -B build -DGGML_AVX_VNNI=ON -DGGML_AVX2=ON -DGGML_F16C=ON"
    echo "    cmake --build build --config Release -j\$(nproc)"
    echo "    sudo cp build/bin/llama-server /usr/local/bin/"
    exit 1
fi
echo "[OK] llama-server: $(command -v "$LLAMA_SERVER")"

# ── Download model if missing ─────────────────────────────────────────────────
if [ ! -f "$MODEL_FILE" ]; then
    echo ""
    echo "[WARN] Model file not found: $MODEL_FILE"
    if [ -n "$HF_FALLBACK" ]; then
        echo "[INFO] Download with huggingface-cli:"
        echo "  pip install huggingface_hub"
        echo "  huggingface-cli download $HF_FALLBACK --include \"*${QUANT}*\" --local-dir $MODELS_DIR"
    fi
    echo "Set MODELS_DIR to the directory containing your GGUF files."
    exit 1
fi
echo "[OK] Model file: $MODEL_FILE ($(du -sh "$MODEL_FILE" | cut -f1))"

# ── CWF-specific tuning ───────────────────────────────────────────────────────
# AVX-VNNI: llama.cpp auto-detects on CWF (E-core Darkmont supports VNNI 256-bit)
# -ngl 0: no GPU layers (CPU-only)
# -t: threads = inference cores (no SMT on CWF, 1:1 core:thread)
# --batch-size: prompt evaluation batch (larger = better prefill throughput)
# --ubatch-size: micro-batch for decode (tune for token-gen throughput)
# -np: parallel slots for concurrent requests (one per agent instance)

CPU_LIST="0-$((INFERENCE_CORES - 1))"
echo "[INFO] Pinning to CPUs: $CPU_LIST via numactl"

echo ""
echo "--- Starting llama-server (Ctrl+C to stop) ---"

exec numactl --physcpubind="$CPU_LIST" \
    "$LLAMA_SERVER" \
        --model        "$MODEL_FILE" \
        --host         0.0.0.0 \
        --port         "$PORT" \
        --ctx-size     "$CTX_SIZE" \
        --threads      "$INFERENCE_CORES" \
        --threads-batch "$INFERENCE_CORES" \
        --batch-size   "$BATCH_SIZE" \
        --ubatch-size  "$((BATCH_SIZE / 2))" \
        --n-gpu-layers 0 \
        --parallel     "$PARALLEL" \
        --cont-batching \
        --flash-attn \
        --metrics \
        --log-format text
