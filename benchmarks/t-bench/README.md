# T-Bench — Quick Start

> **Tool-Calling Benchmark — lightweight function-calling evaluation**  
> Tests an agent's ability to select the right tool, extract parameters correctly, and complete multi-step workflows.

---

## Overview

| Property | Value |
|---|---|
| Environment | Mock REST API server |
| Agent Type | Function-calling |
| Primary KPI | `tool_accuracy` — % of tasks where correct tool is chosen |
| Secondary KPIs | param_accuracy, workflow_completion, retry_rate |
| RAM | ~1–2 GB |
| Storage | Minimal (<1 GB) |
| **Best for** | Fast iteration, LLM capability screening before heavier benchmarks |

---

## Evaluation Dimensions

| Dimension | What It Measures |
|---|---|
| Tool selection | Did agent choose the right tool for the task? |
| Parameter extraction | Are input parameters correctly populated? |
| Multi-step planning | Does agent correctly sequence multiple tool calls? |
| Error recovery | Can agent detect and recover from tool errors? |
| Workflow completion | Does end-to-end workflow reach the correct outcome? |

---

## CWF Setup

```python
python3 benchmarks/t-bench/setup.py
# options:
python3 benchmarks/t-bench/setup.py --dry-run
```

What it does:
1. Installs T-Bench Python packages (fastapi, uvicorn, requests, jsonschema, pytest)
2. Creates mock REST server (`~/cwf_agentic/tbench/mock_server.py`) on first run

---

## Run

### 1. Start LLM server
T-Bench is very fast — 8B model is sufficient:
```python
python3 scripts/inference/start_llamacpp.py --model 8b --cores 64
```

### 2. Run — integrated runner:
```python
# Full evaluation (all categories)
python3 benchmarks/t-bench/run.py --model 8b --inference-cores 64

# Specific categories
python3 benchmarks/t-bench/run.py --categories tool_selection param_extraction

# Dry-run
python3 benchmarks/t-bench/run.py --dry-run
```

### 2. Start mock API server
```bash
python ~/cwf_agentic/tbench/mock_server.py --port 8001 &
# Verify: curl http://localhost:8001/health
```

### 3. Run evaluation
```bash
export OPENAI_BASE_URL="http://localhost:8000/v1"
export TBENCH_SERVER="http://localhost:8001"
python ~/cwf_agentic/tbench/run_eval.py
```

Results saved to `results/tbench/tbench_results.json`.

---

## Inference Core Scaling Study

T-Bench is fast enough to sweep inference cores systematically:

```bash
for CORES in 16 32 64 128; do
    # Restart LLM server with $CORES, run eval, save to results/tbench/cores_${CORES}/
    bash scripts/inference/start_llamacpp.sh --model 8b --cores $CORES &
    sleep 30  # wait for server warmup
    python ~/cwf_agentic/tbench/run_eval.py
    pkill -f llama-server
done
```

---

## Config File

See [`configs/tbench.yaml`](../../configs/tbench.yaml).

---

## Expected Results (CWF 8B Q4_K_M, 64 cores)

| Metric | Min | Target |
|---|---|---|
| tool_accuracy | 70% | 85%+ |
| param_accuracy | 60% | 80%+ |
| workflow_completion | 50% | 70%+ |

Use T-Bench results to screen model quality before running heavier SWE-bench / OSWorld runs.
