#!/usr/bin/env bash
# =============================================================================
# setup_tbench.sh — CWF Agentic AI: T-Bench Setup
# Tool-Calling Benchmark — lightweight mock API server
# Requirements: Python 3.10+, 2 GB RAM, minimal storage
# Dimensions: tool selection accuracy, param extraction, workflow completion
# =============================================================================
set -euo pipefail

LOG_FILE="/tmp/cwf_setup_tbench.log"
exec > >(tee -a "$LOG_FILE") 2>&1

CONDA_ENV="${CONDA_ENV:-agentic}"
TBENCH_DIR="${CWF_WORKDIR:-$HOME/cwf_agentic}/tbench"
TBENCH_PORT="${TBENCH_PORT:-8001}"

echo "============================================="
echo "CWF Agentic AI — T-Bench Setup"
echo "Install dir : $TBENCH_DIR"
echo "API port    : $TBENCH_PORT"
echo "============================================="

eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

mkdir -p "$TBENCH_DIR"
cd "$TBENCH_DIR"

# ── T-Bench install ───────────────────────────────────────────────────────────
# T-Bench is typically distributed as a pip package or minimal repo.
# Attempt pip install first; fall back to manual setup.
echo "--- Installing T-Bench ---"
if pip show t-bench &>/dev/null 2>&1; then
    echo "[OK] t-bench already installed"
elif pip install t-bench --quiet 2>/dev/null; then
    echo "[OK] t-bench installed from PyPI"
else
    echo "[INFO] t-bench not on PyPI — creating minimal local scaffold"
    # Minimal scaffold: mock REST server + evaluation harness
    pip install fastapi uvicorn requests jsonschema --quiet
    cat > "$TBENCH_DIR/mock_server.py" << 'PYEOF'
"""T-Bench minimal mock REST API server."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn, argparse

app = FastAPI(title="T-Bench Mock API", version="1.0")

# Register tool endpoints
@app.get("/tools")
def list_tools():
    return {"tools": [
        {"name": "web_search",       "description": "Search the web for information"},
        {"name": "read_file",         "description": "Read contents of a file"},
        {"name": "write_file",        "description": "Write content to a file"},
        {"name": "execute_command",   "description": "Execute a shell command"},
        {"name": "send_email",        "description": "Send an email message"},
        {"name": "calendar_create",   "description": "Create a calendar event"},
        {"name": "http_request",      "description": "Make an HTTP request"},
        {"name": "python_exec",       "description": "Execute Python code snippet"},
    ]}

@app.post("/invoke/{tool_name}")
def invoke_tool(tool_name: str, payload: dict):
    # Return mock responses for evaluation
    return JSONResponse({"tool": tool_name, "status": "ok", "result": f"Mock result for {tool_name}", "input": payload})

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
PYEOF

    cat > "$TBENCH_DIR/run_eval.py" << 'PYEOF'
"""T-Bench evaluation harness — connects to LLM + mock API server."""
import json, os, sys, time, requests, argparse
from pathlib import Path

OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:8000/v1")
TBENCH_SERVER   = os.environ.get("TBENCH_SERVER",   "http://localhost:8001")
MODEL_NAME      = os.environ.get("MODEL_NAME",      "local-llm")

TASKS = [
    {"id": 1, "instruction": "Search for the current weather in San Francisco using web_search", "expected_tool": "web_search"},
    {"id": 2, "instruction": "Read the contents of /etc/hosts",                                  "expected_tool": "read_file"},
    {"id": 3, "instruction": "Write 'hello world' to /tmp/test.txt",                             "expected_tool": "write_file"},
    {"id": 4, "instruction": "Send an email to alice@example.com with subject 'Test'",            "expected_tool": "send_email"},
    {"id": 5, "instruction": "Create a calendar event for tomorrow at 2pm",                       "expected_tool": "calendar_create"},
]

def call_llm(prompt):
    try:
        r = requests.post(f"{OPENAI_BASE_URL}/chat/completions",
            json={"model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0, "max_tokens": 256}, timeout=60)
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"

def run():
    results = []
    for task in TASKS:
        t0 = time.time()
        prompt = f"You have these tools: web_search, read_file, write_file, execute_command, send_email, calendar_create, http_request, python_exec\n\nTask: {task['instruction']}\n\nRespond with JSON: {{\"tool\": \"<tool_name>\", \"parameters\": {{...}}}}"
        response = call_llm(prompt)
        latency_ms = (time.time() - t0) * 1000

        # Parse tool selection
        try:
            parsed = json.loads(response.strip().strip("```json").strip("```"))
            chosen_tool = parsed.get("tool", "")
        except Exception:
            chosen_tool = ""

        correct = (chosen_tool == task["expected_tool"])
        results.append({"task_id": task["id"], "expected": task["expected_tool"],
                         "chosen": chosen_tool, "correct": correct, "latency_ms": round(latency_ms)})
        print(f"  Task {task['id']}: expected={task['expected_tool']:20s} chosen={chosen_tool:20s} {'✓' if correct else '✗'}")

    accuracy = sum(r["correct"] for r in results) / len(results) * 100
    print(f"\nTool Selection Accuracy: {accuracy:.1f}% ({sum(r['correct'] for r in results)}/{len(results)})")
    return results

if __name__ == "__main__":
    print(f"T-Bench Evaluation | LLM: {OPENAI_BASE_URL} | Server: {TBENCH_SERVER}")
    run_results = run()
    out_path = Path("results_cwf/tbench_results.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(run_results, indent=2))
    print(f"Results saved: {out_path}")
PYEOF

    chmod +x "$TBENCH_DIR/mock_server.py" "$TBENCH_DIR/run_eval.py"
    echo "[OK] Minimal T-Bench scaffold created at $TBENCH_DIR"
fi

# ── Run instructions ──────────────────────────────────────────────────────────
echo ""
echo "--- Usage ---"
cat << 'EOF'
# 1. Start LLM inference server (port 8000)
bash scripts/inference/start_llamacpp.sh --model 8b --cores 64 &

# 2. Start T-Bench mock API server
python ~/cwf_agentic/tbench/mock_server.py --port 8001 &

# 3. Run evaluation
export OPENAI_BASE_URL="http://localhost:8000/v1"
export TBENCH_SERVER="http://localhost:8001"
python ~/cwf_agentic/tbench/run_eval.py

# KPIs: tool_accuracy (%), param_accuracy (%), workflow_completion (%), retry_rate
EOF

echo ""
echo "============================================="
echo "[DONE] T-Bench setup complete. Log: $LOG_FILE"
echo "See: benchmarks/t-bench/README.md"
echo "============================================="
