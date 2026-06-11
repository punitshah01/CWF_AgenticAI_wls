# AppWorld

## Overview
Evaluates agents that coordinate across 9 real-world apps (Amazon, Spotify, Gmail, Google Calendar, Venmo, Phone, Notes, File Manager, Supervisor) via 457 API endpoints. Tasks require multi-step reasoning: e.g., "book a flight and add it to my calendar". Primary KPI: `task_completion_rate` (tgc/sgc scores).

Upstream: https://github.com/StonyBrookNLP/appworld

---

## Prerequisites

| Item | Requirement |
|---|---|
| OS | CentOS Stream 9 / RHEL 9 (x86_64) |
| Python | **3.11+** (hard requirement from AppWorld) |
| Conda | Miniconda or Anaconda |
| RAM | 16 GB+ |
| Disk | ~10 GB |
| Network | First run only (pip, appworld data download) |

---

## Setup

```bash
python3 benchmarks/appworld/setup.py
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--conda-env` | `appworld` | Conda environment name |
| `--skip-post-install` | off | Skip `appworld install/download/verify` |
| `--dry-run` | off | Print commands without executing |

**Expected output on success:**
```
[SUCCESS] AppWorld setup complete
```

A `.setup_complete` marker is written to `benchmarks/appworld/` on success.

---

## Running

```bash
python3 benchmarks/appworld/run.py --model 70b --dataset test_normal
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--model` | `8b` | LLM preset: `8b`, `32b`, `70b` |
| `--inference-cores` | `64` | CPU cores for LLM inference |
| `--env-cores` | `8` | CPU cores per AppWorld instance |
| `--num-instances` | `1` | Parallel agent instances |
| `--dataset` | `dev` | `dev`, `test_normal`, `test_challenge` |
| `--agent` | `simplified_function_calling_agent` | Agent implementation |
| `--llm-port` | `8000` | LLM API port |
| `--collect-emon` | off | Enable EMON telemetry |
| `--collect-rapl` | on | Enable RAPL power monitoring |
| `--dry-run` | off | Print config without running |

**Results saved to:** `results/appworld/appworld_{model}_{dataset}_{timestamp}/`

---

## Error Reference

| Error Message | Cause | Fix |
|---|---|---|
| `Setup not complete. Run setup.py first` | `.setup_complete` marker missing | Run `python3 benchmarks/appworld/setup.py` |
| `Python 3.11+ required` | Wrong Python version | Use conda env: `conda activate appworld` |
| `appworld: command not found` | Package not installed | Re-run `setup.py` |
| `APPWORLD_ROOT not set` | Missing env var | `export APPWORLD_ROOT=~/cwf_agentic/appworld` |

---

## Troubleshooting

**Verify installation:**
```bash
conda activate appworld
appworld verify tests
```

**Expected scores:** 10–40% task_completion_rate with 70B model.

---

## Results

Output directory: `results/appworld/appworld_{model}_{dataset}_{timestamp}/`

| File | Contents |
|---|---|
| `results.csv` | One row per run: tgc, sgc, num_tasks, runtime, power |
| `results.json` | Structured JSON with system metadata |
| `console_output.log` | Full stdout/stderr |
| `telemetry/` | EMON EDP, RAPL samples |

**KPIs:** `task_completion_rate` (tgc), `sgc`, `pkg_power_w`, `dram_power_w`
