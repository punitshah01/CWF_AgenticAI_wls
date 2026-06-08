# WebArena — Quick Start

> **CMU | NeurIPS 2023 | 812 web tasks across 5 self-hosted services**  
> Tests autonomous web browsing: search, form-fill, navigation, multi-service workflows.

---

## Overview

| Property | Value |
|---|---|
| Upstream | github.com/web-arena-x/webarena |
| Paper | arxiv.org/abs/2307.13854 |
| Tasks | 812 (across 5 web services) |
| Environment | Docker (5 web containers) + Playwright headless Chromium |
| Primary KPI | `success_rate` — % of tasks fully completed |
| RAM | ~12–20 GB (services) + LLM |
| Storage | ~50 GB |

---

## Self-Hosted Services

| Service | Port | Docker Image |
|---|---|---|
| Shopping (Magento) | 7770 | webarena/shopping |
| Shopping Admin (CMS) | 7780 | webarena/shopping_admin |
| Reddit (Postmill) | 9999 | webarena/forum |
| GitLab | 8023 | webarena/gitlab |
| Wikipedia (Kiwix) | 8888 | webarena/wikipedia |
| Map (OSRM) | 3000 | webarena/map |

---

## CWF Setup

```python
python3 benchmarks/webarena/setup.py
# options:
python3 benchmarks/webarena/setup.py --dry-run
python3 benchmarks/webarena/setup.py --registry localhost:5000   # offline
```

What it does:
1. Clones WebArena repo, installs Python deps, installs Playwright
2. Pulls 6 Docker service images (from registry if `--registry` set)
3. Writes `~/.cwf_webarena_env` with endpoint variables

---

## Run

### 1. Start web services
```bash
# Follow environment_docker/README.md in the WebArena repo
# Each service needs to be healthy before running evaluation
source ~/.cwf_webarena_env
```

### 2. Start LLM server
```python
python3 scripts/inference/start_llamacpp.py --model 32b --cores 96
```

### 3. Setup test data + cookies
```python
cd ~/cwf_agentic/webarena
python scripts/generate_test_data.py
mkdir -p ./.auth
python browser_env/auto_login.py
```

### 4. Run evaluation — integrated runner:
```python
# Full run (812 tasks)
python3 benchmarks/webarena/run.py --model 32b --inference-cores 96

# Smoke test (10 tasks)
python3 benchmarks/webarena/run.py --start-idx 0 --end-idx 10

# Dry-run (see config)
python3 benchmarks/webarena/run.py --dry-run
```

Or manual:
```python
python run.py \
    --instruction_path agent/prompts/jsons/p_cot_id_actree_2s.json \
    --test_start_idx 0 \
    --test_end_idx 812 \
    --model local_llm \
    --result_dir ./results_cwf

# Smoke test (first 10 tasks):
python run.py --test_start_idx 0 --test_end_idx 10 --model local_llm --result_dir ./results_smoke
```

---

## CWF Core Partitioning

`run.py` pins Playwright workers to env cores automatically via `--env-cores`.

Web services started with `--cpus` Docker flag pointing to env cores:
```
docker run --cpuset-cpus="64-127" webarena/shopping ...
```

---

## Config File

See [`configs/webarena.yaml`](../../configs/webarena.yaml).

---

## Expected Results (CWF 32B Q4_K_M)

| Metric | Min | Target |
|---|---|---|
| success_rate | 5% | 15%+ |
| avg_steps_per_task | — | <15 |
