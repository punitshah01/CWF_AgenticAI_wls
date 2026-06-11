# WebArena

## Overview
Evaluates autonomous web browsing agents on 812 tasks across 5 self-hosted web services (Magento shopping, Reddit, Wikipedia, GitLab). Each task requires multi-step navigation, form-filling, and cross-service workflows. Primary KPI: `success_rate` (% tasks fully completed).

Upstream: https://github.com/web-arena-x/webarena

---

## Prerequisites

| Item | Requirement |
|---|---|
| OS | CentOS Stream 9 / RHEL 9 (x86_64) |
| Python | 3.10+ |
| Docker CE | Running (`docker ps` works) |
| RAM | 20 GB (services) + LLM model size |
| Disk | ~50 GB |
| Network | First run only (Docker images from CMU mirrors) |

---

## Setup

```bash
python3 benchmarks/webarena/setup.py
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--host` | auto-detect | Server IP/hostname |
| `--model` | `llama3:8b` | Ollama model to pull |
| `--images-dir` | `~/webarena_images` | Where to store Docker image tarballs |
| `--include-gitlab` | off | Enable GitLab container (unstable on RHEL9) |
| `--skip-docker` | off | Skip Docker install (if already running) |
| `--skip-ollama` | off | Skip Ollama install (if using external LLM) |
| `--skip-images` | off | Skip image download/load |
| `--skip-containers` | off | Skip container start/config |
| `--dry-run` | off | Print commands without executing |

**Expected output on success:**
```
[ OK ] WebArena env ready.
[SUCCESS] WebArena setup complete
```

A `.setup_complete` marker is written to `benchmarks/webarena/` on success.

---

## Running

```bash
python3 benchmarks/webarena/run.py --model 70b --inference-cores 144 --env-cores 48
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--model` | `8b` | LLM preset: `8b`, `32b`, `70b` |
| `--inference-cores` | `96` | CPU cores for LLM inference |
| `--env-cores` | `48` | CPU cores for Playwright + containers |
| `--start-idx` | `0` | First task index (inclusive) |
| `--end-idx` | `812` | Last task index (exclusive) |
| `--llm-port` | `11434` | LLM API port (11434=Ollama, 8000=llama.cpp) |
| `--run-id` | auto | Unique label for this run |
| `--collect-emon` | off | Enable EMON telemetry |
| `--collect-rapl` | on | Enable RAPL power monitoring |
| `--emon-warmup` | `60` | Seconds before EMON collection starts |
| `--emon-duration` | `180` | Seconds to collect EMON |
| `--dry-run` | off | Print config without running |

**Results saved to:** `results/webarena/webarena_{model}_{cores}_{tasks}_{timestamp}/`

---

## Error Reference

| Error Message | Cause | Fix |
|---|---|---|
| `Setup not complete. Run setup.py first` | `.setup_complete` marker missing | Run `python3 benchmarks/webarena/setup.py` |
| `IndentationError` in `tokenizers.py` | Tokenizer patch not applied | Re-run `setup.py`; the patch uses regex now |
| `Shopping not ready yet (HTTP 0)` | Magento startup slow | Wait 2-5 min; check `docker logs shopping` |
| `Not running inside a virtual environment` | Wrong Python env | `source ~/webarena_venv/bin/activate` |
| `EMON driver not loaded` | SEP kernel module missing | Run `setup/setup_emon.py` |

---

## Troubleshooting

**Check container health:**
```bash
docker ps | grep -E "shopping|forum|wikipedia"
docker logs shopping -n 50
curl http://localhost:7770
```

**Re-run health check only:**
```bash
python3 benchmarks/webarena/setup.py --skip-docker --skip-ollama --skip-images --skip-containers
```

**Platform tuning (run as root before benchmark):**
```bash
sudo python3 setup/setup_platform.py
```

**Expected success rates:** 5-20% with 70B model on CWF.

---

## Results

Output directory: `results/webarena/webarena_{model}_{cores}_{tasks}_{timestamp}/`

| File | Contents |
|---|---|
| `results.csv` | One row per run: success_rate, num_success, num_total, runtime, power |
| `results.json` | Structured JSON with system metadata + per-run results |
| `console_output.log` | Full stdout/stderr tee'd from the run |
| `telemetry/` | EMON EDP output, RAPL power samples |

**KPIs:** `success_rate` (primary), `tasks_per_hour`, `pkg_power_w`, `dram_power_w`
