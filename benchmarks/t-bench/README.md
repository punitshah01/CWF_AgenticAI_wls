# T-Bench

## Overview
Evaluates LLM function-calling capability across 5 categories: tool selection, parameter extraction, multi-step workflows, error recovery, and workflow completion. Uses a mock REST API server (FastAPI on port 9000) to simulate real tool invocations. Primary KPI: `tool_accuracy` (% correct tool chosen).

---

## Prerequisites

| Item | Requirement |
|---|---|
| OS | CentOS Stream 9 / RHEL 9 (x86_64) |
| Python | 3.10+ |
| Conda | Miniconda or Anaconda |
| RAM | 8 GB+ |
| Disk | ~2 GB |
| Network | First run only (pip packages) |

---

## Setup

```bash
python3 benchmarks/t-bench/setup.py
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--conda-env` | `tbench` | Conda environment name |
| `--python-version` | `3.10` | Python version for conda env |
| `--dry-run` | off | Print commands without executing |

**Expected output on success:**
```
[SUCCESS] T-Bench setup complete
```

A `.setup_complete` marker is written to `benchmarks/t-bench/` on success.

---

## Running

```bash
python3 benchmarks/t-bench/run.py --model 8b --categories tool_selection param_extraction
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--model` | `8b` | LLM preset: `8b`, `32b`, `70b` |
| `--inference-cores` | `64` | CPU cores for LLM inference |
| `--categories` | all 5 | Space-separated list of categories to run |
| `--llm-port` | `8000` | LLM API port |
| `--mock-port` | `9000` | FastAPI mock server port |
| `--collect-emon` | off | Enable EMON telemetry |
| `--collect-rapl` | on | Enable RAPL power monitoring |
| `--dry-run` | off | Print config without running |

**Available categories:** `tool_selection`, `param_extraction`, `multi_step`, `error_recovery`, `workflow_completion`

**Results saved to:** `results/tbench/tbench_{model}_{timestamp}/`

---

## Error Reference

| Error Message | Cause | Fix |
|---|---|---|
| `Setup not complete. Run setup.py first` | `.setup_complete` marker missing | Run `python3 benchmarks/t-bench/setup.py` |
| `Connection refused on port 9000` | Mock server not started | Runner starts it automatically; check port conflict |
| `Model does not support function calling` | LLM not function-call capable | Use Llama 3.1+ or a function-calling model |

---

## Troubleshooting

**Check mock server:**
```bash
curl http://localhost:9000/health
```

**Expected scores:** 70–85% tool_accuracy with 70B model.

---

## Results

Output directory: `results/tbench/tbench_{model}_{timestamp}/`

| File | Contents |
|---|---|
| `results.csv` | One row per run: tool_accuracy, param_accuracy, workflow_complete |
| `results.json` | Structured JSON with per-category breakdown |
| `console_output.log` | Full stdout/stderr |
| `telemetry/` | EMON EDP, RAPL samples |

**KPIs:** `tool_accuracy` (primary), `param_accuracy`, `workflow_completion`, `pkg_power_w`
