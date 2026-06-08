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

```bash
bash scripts/setup/setup_appworld.sh
```

What it does:
1. `pip install appworld`
2. `appworld install` — downloads data bundles (~2-3 min)
3. `appworld download data`
4. `appworld verify tests && appworld verify tasks`
5. Clones experiments repo, installs simplified agent

---

## Run

### 1. Start LLM server
AppWorld is lightweight — 8B model is sufficient for pipeline validation:
```bash
bash scripts/inference/start_llamacpp.sh --model 8b --cores 64
```

### 2. Set LLM endpoint
```bash
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="not-needed"
```

### 3. Quick dev validation
```bash
conda activate agentic
appworld run auto \
    --agent-name simplified_function_calling_agent \
    --model-name local-llm \
    --dataset-name dev
```

### 4. Full test_normal
```bash
appworld run auto \
    --agent-name simplified_function_calling_agent \
    --model-name local-llm \
    --dataset-name test_normal

appworld evaluate cwf_baseline test_normal
```

### 5. Hard tasks
```bash
appworld run auto \
    --agent-name simplified_function_calling_agent \
    --model-name local-llm \
    --dataset-name test_challenge

appworld evaluate cwf_challenge test_challenge
```

---

## Multi-Instance Scaling on CWF

AppWorld's Python server is very lightweight. Scale to 4–8 instances easily:

```bash
# Instance 1 (port 5000, LLM port 8000, env cores 64-71)
taskset -c 64-71 appworld run auto --dataset-name test_normal &

# Instance 2 (port 5001, same LLM)
# AppWorld supports --port override; or run in separate virtualenvs
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
