# CWF Agentic AI Workloads

[![Platform](https://img.shields.io/badge/Platform-Clearwater%20Forest-0054ae?style=flat-square&logo=intel)](https://www.intel.com)
[![Core Type](https://img.shields.io/badge/Core-E--core%20Darkmont-00aeef?style=flat-square)](https://www.intel.com)
[![Benchmarks](https://img.shields.io/badge/Benchmarks-5%20Suites-1b8a3e?style=flat-square)](#benchmarks)
[![LLM Inference](https://img.shields.io/badge/Inference-vLLM%20%7C%20llama.cpp-7c5cfc?style=flat-square)](#inference-engines)
[![License](https://img.shields.io/badge/License-Intel%20Internal-gray?style=flat-square)](#)

> **Intel-internal characterization harness** for measuring Agentic AI workload performance on the **Intel Clearwater Forest (CWF)** Xeon platform — E-core Darkmont, 12-channel DDR5, AVX-VNNI.
>
> "Agentic AI" in this context means LLM-powered autonomous agents that use tools, browse the web, write and execute code, operate desktop GUIs, and call REST APIs to complete multi-step tasks — **without human intervention per step**. Unlike static inference benchmarks, these workloads stress the full hardware stack: LLM decode throughput, memory bandwidth, I/O, and OS scheduling under parallel agent concurrency.
>
> POC: Amruta Misra · DPG PAIV SO · Platform PnP Benchmark Suite

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Platform Model](#platform-model)
- [Benchmarks](#benchmarks)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Inference Engines](#inference-engines)
- [Scaling Study](#scaling-study)
- [KPIs & Metrics](#kpis--metrics)
- [Results Format](#results-format)
- [Offline / Air-gapped Setup](#offline--air-gapped-setup)

---

## Prerequisites

| Requirement | Details |
|---|---|
| **OS** | Ubuntu 20.04 / 22.04 / 24.04 or RHEL / CentOS 8/9 (x86\_64) |
| **Python** | 3.11+ (enforced at runtime; 3.10+ for non-AppWorld workloads) |
| **Conda** | Miniconda or Anaconda — auto-installed if missing |
| **Docker CE** | With `docker compose` plugin — required for SWE-bench, WebArena, OSWorld |
| **KVM / VT-x** | BIOS VT-x enabled — required for **OSWorld only** |
| **RAM** | Min 32 GB; recommended **64+ GB** (OSWorld: 8 GB per VM) |
| **Disk** | SWE-bench ≥ 120 GB · WebArena ≥ 50 GB · OSWorld ≥ 100 GB · AppWorld ≥ 10 GB |
| **Network** | Required on first run (Docker Hub, HuggingFace, GitHub); see [Offline Setup](#offline--air-gapped-setup) |
| **numactl** | For CPU pinning — installed by `scripts/setup.py` |

---

## Platform Model

| Attribute | Value |
|---|---|
| Codename | **Clearwater Forest (CWF)** |
| CPU Family / Model | 6 / 221 |
| Core Type | E-core (Darkmont) — **no HyperThreading** |
| Cores per Socket | 144–288 (SKU dependent) |
| Threads per Core | **1** (no SMT) |
| L2 Cache | 4 MB per module (4 cores share) |
| Memory | 12-channel DDR5 |
| Vector Extensions | AVX-VNNI (256-bit, INT8 matmul) |
| KVM | Yes (VT-x) — required for OSWorld |

**Two-domain compute model:**
- **LLM Inference (Brain):** Memory-BW bound, vectorized matmul — 50–70% of cores, numactl-pinned
- **Environment Execution (Body):** I/O heavy, Docker/KVM orchestration — 20–40% of cores, cgroup cpuset

---

## Benchmarks

Each benchmark has its own `setup.py` and `run.py` under `benchmarks/<name>/`.

| Dir | Benchmark | What the Agent Does | KPI | Environment |
|---|---|---|---|---|
| [`benchmarks/swe-bench/`](benchmarks/swe-bench/) | **SWE-bench** | Reads a real GitHub issue, writes a code patch, runs the repo's test suite | `resolve_rate` (% issues fixed) | Docker container per task |
| [`benchmarks/webarena/`](benchmarks/webarena/) | **WebArena** | Controls Playwright/Chromium to complete natural-language tasks across 5 self-hosted web apps (GitLab, Reddit, e-commerce, Wikipedia, map) | `success_rate` (% tasks completed) | 6 Docker service containers |
| [`benchmarks/osworld/`](benchmarks/osworld/) | **OSWorld** | Receives a screenshot of an Ubuntu 22.04 desktop in a QEMU/KVM VM and interacts via simulated keyboard/mouse to complete OS tasks across 9 app domains | `success_rate` (369 tasks) | QEMU/KVM VM per instance |
| [`benchmarks/appworld/`](benchmarks/appworld/) | **AppWorld** | Makes sequential REST API calls across 9 microservices (Spotify, Amazon, Gmail, Venmo, etc.) with 457 endpoints to complete multi-app workflows | `task_completion_rate` + SGC score | Python microservice stack |
| [`benchmarks/t-bench/`](benchmarks/t-bench/) | **T-Bench** | Invokes mock REST API tools with correct parameters; evaluates tool selection, parameter extraction, and multi-step planning | `tool_accuracy` % | In-process mock server |

### Benchmark Resource Summary

| Benchmark | Docker? | KVM? | Internet Needed? | RAM | Disk |
|---|---|---|---|---|---|
| SWE-bench | ✓ required | — | First run (Docker Hub + GitHub) | 4–8 GB/worker | ~120 GB |
| WebArena | ✓ required | — | First run (Docker Hub) | 12–20 GB | ~50 GB |
| OSWorld | ✓ required | ✓ required | First run (HuggingFace VM images) | 8 GB/VM | ~100 GB |
| AppWorld | — | — | First run (`appworld install`) | 2–4 GB | ~10 GB |
| T-Bench | — | — | pip packages only | 1–2 GB | <1 GB |

---

## Repository Structure

```
CWF_AgenticAI_wls/
├── README.md                        # This file
├── docs/
│   └── index.html                   # Full interactive HTML test plan
├── benchmarks/
│   ├── swe-bench/
│   │   ├── setup.py                 # Install SWE-bench dependencies
│   │   ├── run.py                   # Run SWE-bench evaluation + telemetry
│   │   └── README.md
│   ├── webarena/
│   │   ├── setup.py
│   │   ├── run.py
│   │   └── README.md
│   ├── osworld/
│   │   ├── setup.py
│   │   ├── run.py
│   │   └── README.md
│   ├── appworld/
│   │   ├── setup.py
│   │   ├── run.py
│   │   └── README.md
│   └── t-bench/
│       ├── setup.py
│       ├── run.py
│       └── README.md
├── scripts/
│   ├── setup.py                     # Unified dependency installer (all benchmarks)
│   ├── prefetch_assets.py           # One-time asset downloader + registry mirror
│   └── inference/
│       ├── start_vllm.py            # vLLM server (CWF-optimized, CPU/OpenVINO)
│       └── start_llamacpp.py        # llama.cpp server (GGUF + AVX-VNNI)
├── setup/
│   ├── setup_docker.py              # Docker CE installer
│   ├── setup_emon.py                # Intel SEP/EMON installer
│   └── README.md
├── configs/
│   ├── assets.yaml                  # Canonical asset manifest (Docker images, model files)
│   ├── swebench.yaml                # SWE-bench run parameters
│   ├── webarena.yaml
│   ├── osworld.yaml
│   ├── appworld.yaml
│   └── tbench.yaml
├── common/                          # Shared Python utilities (the "common setup/runtime layer")
│   ├── cpu_info.py                  # CPUInfo: lscpu topology
│   ├── os_info.py                   # OSInfo: BIOS, microcode, kernel
│   ├── platform_info.py             # detect_platform(): CWF/DMR/GNR/...
│   ├── system_metadata.py           # Full system snapshot OrderedDict
│   ├── csv_writer.py                # Smart CSV append
│   ├── json_results.py              # Structured JSON output
│   ├── setup_utils.py               # Shared helpers for every benchmarks/*/setup.py
│   │                                 #   (log, banner, run, pip_install, ensure_conda_env, ...)
│   └── telemetry/
│       ├── emon.py                  # EMON collection + EDP post-processing
│       ├── rapl.py                  # RAPL power via powercap sysfs
│       ├── ssmon.py                 # SSMON temperature (CWF/DMR/GNR/SRF)
│       ├── ptat.py                  # PTAT temperature (older platforms)
│       └── manager.py              # TelemetryManager: unified facade
├── misc/                            # CLI utility scripts
│   ├── detect_platform.py
│   ├── check_emon_setup.py
│   ├── collect_rapl.py
│   ├── collect_meminfo.py
│   ├── process_emon.py
│   └── read_emon_csv.py
└── results/
    ├── .gitkeep
    └── README.md
```

---

## Quick Start

### Step 0 — Shared/common setup (run once per machine)

```bash
# Installs base OS packages, Docker, conda, common Python deps, and
# (with --install-emon) the Intel SEP/EMON telemetry stack.
# This is the SINGLE place common functionality is installed — every
# benchmark's own setup.py builds on top of this.
python3 scripts/setup.py --install-emon
```

### Step 1 — Workload-specific setup

```bash
# Apply platform tuning (run as root) — optional, improves run-to-run consistency
sudo python3 setup/setup_platform.py

# Install per-benchmark dependencies (container setup, task data, benchmark repo
# clones — anything NOT already handled by scripts/setup.py above)
python3 benchmarks/appworld/setup.py       # lightest — start here
python3 benchmarks/t-bench/setup.py
python3 benchmarks/swe-bench/setup.py
python3 benchmarks/webarena/setup.py
python3 benchmarks/osworld/setup.py        # requires KVM/VT-x in BIOS
```

### Step 2 — Start LLM inference server

```bash
# llama.cpp (fast startup, GGUF)
python3 scripts/inference/start_llamacpp.py --model 8b --cores 64

# vLLM (higher throughput, OpenVINO backend)
python3 scripts/inference/start_vllm.py --model 32b --cores 96
```

### Step 3 — Run a benchmark

```bash
# Smoke test
python3 benchmarks/appworld/run.py --model 8b --dataset dev --dry-run

# SWE-bench Lite
python3 benchmarks/swe-bench/run.py --model 32b --split lite --max-workers 8

# WebArena (10-task smoke test)
python3 benchmarks/webarena/run.py --model 8b --start-idx 0 --end-idx 10

# OSWorld
python3 benchmarks/osworld/run.py --model 32b --num-envs 4 --obs-type screenshot

# T-Bench
python3 benchmarks/t-bench/run.py --model 8b
```

Results land in `results/<benchmark>/<run_id>/results.csv` and `results.json`.

---

## Common Troubleshooting

| Problem | Fix |
|---|---|
| `Setup not complete. Run setup.py first` | Run `python3 benchmarks/<name>/setup.py` |
| `Not running inside a virtual environment` | `source .venv/bin/activate` or `conda activate <env>` |
| `EMON driver not loaded` | `sudo /opt/intel/sep/sepdk/src/insmod-sep -r -g root` |
| Docker permission denied | `sudo systemctl start docker` |
| Shopping/service not ready | `docker logs shopping -n 50`; wait 2-5 min for Magento |
| KVM not available | Enable VT-x/AMD-V in BIOS; verify with `egrep -c '(vmx|svm)' /proc/cpuinfo` |
python3 benchmarks/webarena/run.py --model 32b --start-idx 0 --end-idx 10

# OSWorld
python3 benchmarks/osworld/run.py --model 32b --num-envs 4 --obs-type screenshot

# T-Bench
python3 benchmarks/t-bench/run.py --model 8b
```

Results land in `results/<benchmark>/<run_id>/results.csv` and `results.json`.

---

## Environment Variables

| Variable | Used By | Description | Default |
|---|---|---|---|
| `REGISTRY_URL` | `scripts/setup.py`, `scripts/prefetch_assets.py` | Docker registry for offline image pulls (e.g. `localhost:5000`) | `""` (Docker Hub) |
| `MINICONDA_LOCAL` | `scripts/setup.py` | Path to cached Miniconda installer (skips download) | Miniconda3 installer (see `setup/setup_venv.py`) |
| `PIP_CACHE_DIR` | `scripts/setup.py` | Shared pip wheel cache directory | pip default |
| `OPENAI_BASE_URL` | `benchmarks/appworld/run.py` | LLM server OpenAI-compatible API base URL | `http://localhost:8000/v1` |
| `OPENAI_API_KEY` | `benchmarks/appworld/run.py` | API key (any non-empty string for local server) | `not-needed` |
| `HOSTURL` | `~/.cwf_webarena_env` | Host running WebArena Docker services | `localhost` |
| `OMP_NUM_THREADS` | `scripts/inference/start_vllm.py`, `start_llamacpp.py` | OpenMP threads (set to `--cores` value) | auto |
| `OV_TELEMETRY_OPTOUT` | `scripts/inference/start_vllm.py` | Disable OpenVINO telemetry | `1` |

---

## Inference Engines

| Engine | Backend | Best For | Default Quant |
|---|---|---|---|
| **llama.cpp** | GGML/GGUF + AVX-VNNI | Single-instance, fast startup, offline | Q4\_K\_M |
| **vLLM** | CPU/OpenVINO backend | Multi-instance serving, higher throughput | INT8 |

Start with llama.cpp for initial validation (faster startup, predictable memory usage).  
Switch to vLLM for production characterization runs with `--num-instances > 1`.

```python
# Download GGUF models (one-time, requires internet)
python3 scripts/prefetch_assets.py pull-models --models 8b 32b

# Then use offline:
python3 scripts/inference/start_llamacpp.py --model 8b --models-dir assets/models
```

---

## Scaling Study

### Phase 1: Single-Instance Core Scaling

| Inference Cores | Env Cores | Topology Boundary |
|---|---|---|
| 16 | 8 | 4 modules |
| 32 | 16 | 8 modules |
| 64 | 16 | 16 modules (½ socket) |
| 96 | 32 | 24 modules |
| 128 | 32 | 32 modules (full socket on some SKUs) |
| 192+ | 48 | Full platform |

### Phase 2: Multi-Instance Throughput

| Instances | Cores/Instance | Total | KPI Goal |
|---|---|---|---|
| 1 | 64+16 | 80 | Baseline |
| 2 | 64+16 | 160 | Linear check |
| 4 | 32+8 | 160 | Same cores, more parallelism |
| 8 | 16+8 | 192 | Throughput peak |

---

## KPIs & Metrics

| Category | Metric | Unit |
|---|---|---|
| LLM Inference | Decode tokens/sec | tok/s |
| LLM Inference | Time-to-first-token (TTFT) | ms |
| Throughput | Tasks completed per hour | tasks/hr |
| Efficiency | Tasks per watt-hour | tasks/Wh |
| Microarch | IPC, LLC MPKI, Mem BW % | EMON |
| SWE-bench | `resolve_rate` | % |
| WebArena | `success_rate` | % |
| OSWorld | `success_rate` | % |
| AppWorld | `task_completion_rate`, SGC | % |
| T-Bench | `tool_accuracy` | % |

---

## Results Format

See [`results/README.md`](results/README.md). Each run writes:
- `results/<benchmark>/<run_id>/results.csv` — flat row with all system + benchmark KPIs
- `results/<benchmark>/<run_id>/results.json` — structured JSON with system metadata, results, EMON, RAPL
- `results/<benchmark>/<run_id>/telemetry/` — raw EMON data + EDP output

---

## Offline / Air-gapped Setup

```python
# On a machine with internet access — pull everything once:
python3 scripts/prefetch_assets.py start-registry          # local registry on :5000
python3 scripts/prefetch_assets.py pull                    # Docker images + VM images
python3 scripts/prefetch_assets.py pull-models --models 8b 32b  # GGUF models
python3 scripts/prefetch_assets.py push --registry localhost:5000

# On SUT (no internet):
python3 scripts/setup.py --registry localhost:5000 --pip-cache-dir /data/pip-cache
python3 scripts/inference/start_llamacpp.py --models-dir /data/models --model 8b

# Air-gapped transfer (no network between machines):
python3 scripts/prefetch_assets.py export-tar --out /data/cwf_assets.tar.gz
# ... copy file to SUT ...
python3 scripts/prefetch_assets.py import-tar --in /data/cwf_assets.tar.gz
```

---

## Documentation

📄 **[Full HTML Test Plan → docs/index.html](docs/index.html)**

Includes platform architecture, benchmark deep-dives, scaling study design, EMON strategy, execution timeline, and risk/mitigation table.

---

*Intel Confidential | DPG PAIV SO | Clearwater Forest Agentic AI Workload Characterization*
