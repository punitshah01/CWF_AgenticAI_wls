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

```bash
bash scripts/setup/setup_webarena.sh
```

What it does:
1. Clones WebArena repo, installs Python deps, installs Playwright
2. Prints Docker service startup instructions
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
```bash
bash scripts/inference/start_llamacpp.sh --model 32b --cores 96
```

### 3. Setup test data + cookies
```bash
cd ~/cwf_agentic/webarena
source ~/.cwf_webarena_env
python scripts/generate_test_data.py
mkdir -p ./.auth
python browser_env/auto_login.py
```

### 4. Run evaluation
```bash
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

```bash
# Pin Playwright browser workers to env cores only
taskset -c 64-143 python run.py ...
```

Web services should be started with `--cpus` Docker flag pointing to env cores:
```bash
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
