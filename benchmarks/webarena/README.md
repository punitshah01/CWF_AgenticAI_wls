# WebArena on CWF — Setup & Run Guide

> **CMU | NeurIPS 2023 | 812 web tasks across 5 self-hosted services**  
> Tests autonomous web browsing: search, form-fill, navigation, multi-service workflows.

---

## Overview

| Property | Value |
|---|---|
| Upstream | github.com/web-arena-x/webarena |
| Tasks | 812 (across 5 web services) |
| Environment | Docker (5 web containers) + Playwright headless Chromium |
| Primary KPI | `success_rate` — % of tasks fully completed |
| RAM required | ~12–20 GB (services) + LLM model size |
| Storage required | ~50 GB |

---

## Self-Hosted Web Services

| Service | Port | Container |
|---|---|---|
| Shopping (Magento) | 7770 | webarena/shopping |
| Shopping Admin | 7780 | webarena/shopping_admin |
| Reddit (Postmill) | 9999 | webarena/forum |
| Wikipedia (Kiwix) | 8888 | webarena/wikipedia |
| Map (OSRM) | 3000 | webarena/map |
| GitLab | 8023 | webarena/gitlab *(disabled by default — unstable on RHEL9)* |

---

## Prerequisites

- CentOS Stream 9 (or RHEL 9) — tested on CWF BKC kernel `6.14.0-cwf.*`
- Python 3.9+ (system Python is fine for setup; benchmark itself uses conda `agentic` env)
- Docker CE installed and running (`docker ps` should work)
- Root or sudo access (for EMON driver loading and platform tuning)
- ~50 GB free disk space

---

## Step-by-Step Setup

### Step 1 — Clone the repo (first time only)

```bash
git clone https://github.com/punitshah01/CWF_AgenticAI_wls.git ~/CWF_AgenticAI_wls
cd ~/CWF_AgenticAI_wls
```

If already cloned:
```bash
cd ~/CWF_AgenticAI_wls
git pull
```

---

### Step 2 — Common infrastructure (Miniconda + Docker + EMON)

```bash
python3 scripts/setup.py --install-emon
```

This installs (idempotent — safe to re-run):
1. Base system packages (gcc, wget, numactl, perf, …)
2. Docker CE
3. Miniconda → `agentic` conda env (Python 3.11)
4. git-lfs
5. Common Python packages into the `agentic` env
6. Intel SEP/EMON drivers

**After it finishes, activate conda:**
```bash
source ~/.bashrc
conda activate agentic
# OR if that doesn't work:
source ~/miniconda3/etc/profile.d/conda.sh
conda activate agentic
```

Your prompt should now show `(agentic)`.

---

### Step 3 — Platform tuning (run as root, recommended)

```bash
sudo bash setup/setup_platform.sh
```

Sets CPU governor → `performance`, disables ASLR, sets THP to `madvise`.  
Reboot to restore defaults.

---

### Step 4 — Verify EMON

```bash
python3 misc/check_emon_setup.py
```

Expected output (all OK):
```
  [ OK ]  SEP installed              /opt/intel/sep/bin64/emon
  [ OK ]  SEP version                5.58 (need >= 5.32)
  [ OK ]  SEP drivers                sep + pax drivers loaded
  [ OK ]  pyedp / edp.rb             /opt/intel/sep/.../pyedp.py
```

If drivers are not loaded:
```bash
sudo /opt/intel/sep/sepdk/src/insmod-sep -r -g root
```

---

### Step 5 — WebArena-specific setup

```bash
conda activate agentic
python3 benchmarks/webarena/setup.py
```

This will:
1. Clone the WebArena repo into `~/cwf_agentic/webarena`
2. Install all WebArena Python packages (playwright, gymnasium, openai 0.27, …)
3. Install Playwright Chromium browser
4. Pull Docker images for all web services
5. Write `~/.cwf_webarena_env` with service endpoint variables

Dry-run to preview:
```bash
python3 benchmarks/webarena/setup.py --dry-run
```

For offline/airgapped environments with a local registry:
```bash
python3 benchmarks/webarena/setup.py --registry localhost:5000
```

---

### Step 6 — Start web services

```bash
source ~/.cwf_webarena_env

# Start all containers (follow the WebArena repo's environment_docker/README.md)
# Quick check that services are up:
docker ps
curl -s http://localhost:7770 | head -3   # shopping
curl -s http://localhost:9999 | head -3   # reddit
```

---

### Step 7 — Generate test data and login cookies

```bash
cd ~/cwf_agentic/webarena
python scripts/generate_test_data.py
mkdir -p .auth
python browser_env/auto_login.py
```

---

### Step 8 — Start LLM inference server

```bash
# Option A: Ollama (easiest)
ollama serve &
ollama pull llama3.1:8b

# Option B: llama.cpp server pinned to inference cores
taskset -c 0-63 python3 scripts/inference/start_llamacpp.py \
    --model /path/to/model.gguf --port 8000
```

---

## Running the Benchmark

### Canonical runner (recommended)

```bash
# Full 812-task run with EMON
bash benchmarks/webarena/run_webarena.sh \
    --model 8b \
    --inference-cores 0-63 \
    --env-cores 64-127 \
    --collect-emon \
    --output-dir results/webarena_$(date +%Y%m%d)

# Smoke test — first 10 tasks, no EMON
bash benchmarks/webarena/run_webarena.sh \
    --model 8b \
    --start-idx 0 --end-idx 10 \
    --output-dir results/webarena_smoke

# Dry-run (prints commands, nothing executed)
python3 benchmarks/webarena/run_webarena.py --dry-run --output-dir /tmp/test
```

### With a custom config

```bash
bash benchmarks/webarena/run_webarena.sh \
    --config benchmarks/webarena/config/default_config.yaml \
    --output-dir results/webarena_custom
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `8b` | LLM preset: `8b`, `32b`, `70b` |
| `--inference-cores` | `0-63` | CPU range for LLM server |
| `--env-cores` | `64-127` | CPU range for Playwright + Docker |
| `--start-idx` | `0` | First task index |
| `--end-idx` | `812` | Last task index (exclusive) |
| `--llm-port` | `11434` | LLM API port (11434=Ollama, 8000=llama.cpp) |
| `--collect-emon` | off | Enable Intel EMON telemetry |
| `--collect-rapl` | on | Enable RAPL power monitoring |
| `--output-dir` | `results` | Output directory |
| `--config` | — | YAML config file path |
| `--dry-run` | off | Print commands without running |
| `--verbose` | off | DEBUG-level logging |

---

## Output Files

All outputs land in `--output-dir`:

| File | Contents |
|------|----------|
| `run.log` | Full stdout + stderr (written by `run_webarena.sh`) |
| `results.json` | Score, per-task pass/fail, platform metadata, git SHA |
| `results.csv` | Per-task rows for analysis |
| `emon_*.emon` | Raw EMON counter data *(only with `--collect-emon`)* |

---

## Config File

The canonical config is at:
```
benchmarks/webarena/config/default_config.yaml
```

Key fields:

```yaml
model: "local-llm"
max_steps: 30
timeout_seconds: 1800
output_dir: "results/webarena"

services:
  shopping: "localhost:7770"
  reddit:   "localhost:9999"
  gitlab_enabled: false      # disabled by default (unstable on RHEL9/overlay2)

topology:
  inference_cores: "0-63"
  env_cores:       "64-127"
  metrics_cores:   "128-143"
```

---

## CWF Core Partitioning

```
Cores 0–63    →  LLM inference server (llama.cpp / Ollama)
Cores 64–127  →  Playwright workers + Docker web services
Cores 128–143 →  Orchestration + metrics collection
```

---

## Known Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `conda: command not found` after setup | Shell hasn't sourced new PATH | `source ~/.bashrc` or `source ~/miniconda3/etc/profile.d/conda.sh` |
| GitLab container returns 500 | overlay2 + RHEL9 kernel conflict | Keep `gitlab_enabled: false` in config |
| SEP version shows "unknown" | Beta build version string format | Fixed in `check_emon_setup.py` — `git pull` to get the fix |
| `tar: does not look like a tar archive` | Partial/corrupt SEP download | Fixed — setup now validates and re-downloads automatically |
| `openai` version conflicts | WebArena requires `openai==0.27.0` | Use the dedicated `agentic` conda env; don't mix with other benchmarks |

---

## Expected Results (CWF, 32B Q4_K_M)

| Metric | Typical range |
|--------|--------------|
| `success_rate` | 5–20% |
| `avg_steps_per_task` | 8–20 |
| Runtime (full 812 tasks) | 6–12 hours |
