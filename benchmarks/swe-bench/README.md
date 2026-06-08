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

```bash
bash scripts/setup/setup_swebench.sh
```

What it does:
1. Clones `github.com/SWE-bench/SWE-bench`
2. `pip install -e .[test]` in conda `agentic`
3. Validates gold-patch on 1 task (sympy__sympy-20590)

---

## Run

### 1. Start LLM server
```bash
bash scripts/inference/start_llamacpp.sh --model 32b --cores 96
# or
bash scripts/inference/start_vllm.sh --model 32b --cores 96
```

### 2. Generate agent predictions
Using SWE-agent (recommended):
```bash
conda activate agentic
cd ~/cwf_agentic/swebench
python -m sweagent.run.run_batch \
    --config config/default.yaml \
    --agent.model.name local-llm \
    --agent.model.base_url http://localhost:8000/v1 \
    --env.repo.base_commit HEAD \
    --instances.type swe_bench \
    --instances.dataset_name princeton-nlp/SWE-bench_Lite \
    --instances.split test
```

### 3. Evaluate
```bash
python -m swebench.harness.run_evaluation \
    --dataset_name princeton-nlp/SWE-bench_Lite \
    --predictions_path <path_to_predictions.jsonl> \
    --max_workers 8 \
    --run_id cwf_baseline
```

---

## CWF Scaling Notes

- `max_workers` = number of parallel Docker containers
- Each container uses ~4–8 GB RAM and ~4 cores burst
- **CWF BKM:** `max_workers = min(int(0.75 * nproc), 24)`
- Pin containers to env cores: set `DOCKER_CPUSET="64-143"` and use `--cpuset-cpus` in Docker run args
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
