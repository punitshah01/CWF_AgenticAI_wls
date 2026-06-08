# SWE-bench — Quick Start

> **Princeton NLP | ICLR 2024 Oral | 2,294 real GitHub issues**  
> Tests whether an LLM agent can resolve real software bugs by writing patches.

---

## Overview

| Property | Value |
|---|---|
| Upstream | github.com/SWE-bench/SWE-bench |
| Paper | arxiv.org/abs/2310.06770 |
| Dataset | SWE-bench Lite (300) / Verified (500) / Full (2294) |
| Environment | Docker containers (per-task repo + test suite) |
| Primary KPI | `resolve_rate` — % of tasks where agent patch passes tests |
| RAM | ~4–8 GB per worker |
| Storage | ~120 GB (Docker images) |

---

## CWF Setup

```python
python3 benchmarks/swe-bench/setup.py
# options:
python3 benchmarks/swe-bench/setup.py --dry-run
python3 benchmarks/swe-bench/setup.py --registry localhost:5000   # offline
python3 benchmarks/swe-bench/setup.py --skip-post-install
```

What it does:
1. Clones `github.com/SWE-bench/SWE-bench`
2. `pip install -e .[test]` in conda `agentic`
3. Validates gold-patch on 1 task (sympy__sympy-20590)

---

## Run

### 1. Start LLM server
```python
python3 scripts/inference/start_llamacpp.py --model 32b --cores 96
# or
python3 scripts/inference/start_vllm.py --model 32b --cores 96
```

### 2. Generate agent predictions  (or use run.py below)
Using SWE-agent (recommended):
```python
conda activate agentic
cd ~/cwf_agentic/swebench
python -m sweagent.run.run_batch \
    --config config/default.yaml \
    --agent.model.name local-llm \
    --agent.model.base_url http://localhost:8000/v1 \
    --env.repo.base_commit HEAD \
    --instances.type swe_bench \
    --instances.dataset_name SWE-bench/SWE-bench_Lite \
    --instances.split test
```

### 3. Evaluate — or use the integrated runner:
```python
# Integrated: setup + run + telemetry in one command
python3 benchmarks/swe-bench/run.py --model 32b --inference-cores 96
python3 benchmarks/swe-bench/run.py --split lite --max-workers 8 --collect-rapl
python3 benchmarks/swe-bench/run.py --dry-run   # preview config
```

Manual evaluate only:
```python
python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Lite \
    --predictions_path <path_to_predictions.jsonl> \
    --max_workers 8 \
    --run_id cwf_baseline
    # CWF is x86_64 — no --namespace '' needed (ARM-only flag)
```

---

## CWF Scaling Notes

- `max_workers` = number of parallel Docker containers
- Each container uses ~4–8 GB RAM and ~4 cores burst
- **Upstream BKM:** `max_workers = min(int(0.75 * os.cpu_count()), 24)`
- `run.py --max-workers` enforces this automatically
- Pin containers to env cores: `--env-cores 32` in `run.py` sets taskset automatically
- Leave cores 0–63 for LLM inference

| max_workers | Parallelism | Notes |
|---|---|---|
| 1 | Serial | Validation only |
| 4 | Low | ~16 GB RAM used |
| 8 | Recommended | ~32 GB RAM |
| 16 | High | ~64 GB RAM |
| 24 | Max CWF | ~96 GB RAM |

---

## Config File

See [`configs/swebench.yaml`](../../configs/swebench.yaml) for all tunable parameters.

---

## Expected Results (CWF 32B Q4_K_M)

| Metric | Min | Target | Stretch |
|---|---|---|---|
| resolve_rate (Lite) | 5% | 15%+ | 25%+ |
| avg_time_per_task | — | <5 min | <3 min |
