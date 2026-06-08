# AppWorld — Quick Start

> **Stony Brook NLP | ACL 2024 Best Resource | 750 multi-app tasks**  
> Tests agents that coordinate across 9 real-world apps via 457 API endpoints.

---

## Overview

| Property | Value |
|---|---|
| Upstream | github.com/StonyBrookNLP/appworld |
| Paper | arxiv.org/abs/2407.18901 |
| Tasks | 750 (dev + test_normal + test_challenge) |
| Apps | Amazon, Spotify, Gmail, Google Calendar, Venmo, Phone, Supervisor, Notes, File Manager |
| APIs | 457 endpoints |
| Environment | Python microservices (in-memory DBs) |
| Primary KPI | `task_completion_rate` — % of tasks fully solved |
| Secondary KPI | SGC (Soft Goal Completion) score |
| RAM | ~2–4 GB per instance |
| Storage | ~10 GB |

---

## CWF Setup

```python
python3 benchmarks/appworld/setup.py
# options:
python3 benchmarks/appworld/setup.py --dry-run
python3 benchmarks/appworld/setup.py --skip-post-install
```

What it does:
1. `pip install appworld` (Python 3.11+ required)
2. `appworld install` — downloads data bundles (~2-3 min)
3. `appworld download data`
4. `appworld verify tests && appworld verify tasks`

---

## Run

### 1. Start LLM server
AppWorld is lightweight — 8B model is sufficient for pipeline validation:
```python
python3 scripts/inference/start_llamacpp.py --model 8b --cores 64
```

### 2. Run — integrated runner:
```python
# Quick dev validation
python3 benchmarks/appworld/run.py --model 8b --dataset dev

# Full test_normal
python3 benchmarks/appworld/run.py --model 32b --dataset test_normal --inference-cores 96

# Hard tasks
python3 benchmarks/appworld/run.py --model 32b --dataset test_challenge

# Multi-instance (4 parallel agents)
python3 benchmarks/appworld/run.py --dataset test_normal --num-instances 4

# Dry-run
python3 benchmarks/appworld/run.py --dry-run
```

Or manual:
```python
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="not-needed"
conda activate agentic
appworld run auto \
    --agent-name simplified_function_calling_agent \
    --model-name local-llm \
    --dataset-name test_normal
appworld evaluate cwf_baseline test_normal
```

---

## Multi-Instance Scaling on CWF

AppWorld's Python server is very lightweight. Scale to 4–8 instances easily:

```python
# Automatic multi-instance via run.py:
python3 benchmarks/appworld/run.py --dataset test_normal --num-instances 4
```

| Instances | RAM | Env Cores | Expected Throughput |
|---|---|---|---|
| 1 | ~3 GB | 4 | Baseline |
| 2 | ~6 GB | 8 | ~1.9× |
| 4 | ~12 GB | 16 | ~3.5× |
| 8 | ~24 GB | 32 | ~6× |

---

## Config File

See [`configs/appworld.yaml`](../../configs/appworld.yaml).

---

## Expected Results (CWF 32B Q4_K_M)

| Dataset | Min | Target | Stretch |
|---|---|---|---|
| test_normal | 10% | 25%+ | 40%+ |
| test_challenge | 5% | 15%+ | 25%+ |
