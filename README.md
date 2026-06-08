# CWF Agentic AI Workloads

[![Platform](https://img.shields.io/badge/Platform-Clearwater%20Forest-0054ae?style=flat-square&logo=intel)](https://www.intel.com)
[![Core Type](https://img.shields.io/badge/Core-E--core%20Darkmont-00aeef?style=flat-square)](https://www.intel.com)
[![Benchmarks](https://img.shields.io/badge/Benchmarks-5%20Suites-1b8a3e?style=flat-square)](#benchmarks)
[![LLM Inference](https://img.shields.io/badge/Inference-vLLM%20%7C%20llama.cpp-7c5cfc?style=flat-square)](#inference-engines)
[![License](https://img.shields.io/badge/License-Intel%20Internal-gray?style=flat-square)](#)

> **Characterization test plan for Agentic AI workloads on Intel Clearwater Forest (CWF) — E-core Darkmont, 12-channel DDR5, AVX-VNNI.**  
> POC: Amruta Misra · DPG PAIV SO · Platform PnP Benchmark Suite

---

## Table of Contents

- [Overview](#overview)
- [Platform Model](#platform-model)
- [Benchmarks](#benchmarks)
- [Inference Engines](#inference-engines)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Scaling Study](#scaling-study)
- [KPIs & Metrics](#kpis--metrics)
- [Results Format](#results-format)
- [Documentation](#documentation)

---

## Overview

This repo contains everything needed to characterize CWF performance under **Agentic AI workloads** — a class of tasks where LLM-powered autonomous agents solve complex multi-step problems by interacting with environments (code repos, web browsers, desktops, APIs).

| Benchmark | What It Tests | Environment | Complexity |
|---|---|---|---|
| **SWE-bench** | Real-world software engineering (GitHub issues) | Docker containers | Medium |
| **WebArena** | Autonomous web browsing & task completion | 5 self-hosted web services + Playwright | High |
| **OSWorld** | Desktop/OS GUI interaction | QEMU/KVM virtual machines | Very High |
| **AppWorld** | Multi-application API workflows | Python microservices (9 apps, 457 APIs) | Medium |
| **T-Bench** | Tool-calling accuracy & execution reliability | Mock REST API server | Low |

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
- **LLM Inference (Brain):** Memory-BW bound, vectorized matmul, 50–70% of cores, numactl-pinned
- **Environment Execution (Body):** I/O heavy, Docker/KVM orchestration, 20–40% of cores, cgroup cpuset

---

## Benchmarks

See [`benchmarks/`](benchmarks/) for per-benchmark quick-start guides.

| Dir | Benchmark | Upstream Repo |
|---|---|---|
| [`benchmarks/swe-bench/`](benchmarks/swe-bench/) | SWE-bench | github.com/SWE-bench/SWE-bench |
| [`benchmarks/webarena/`](benchmarks/webarena/) | WebArena | github.com/web-arena-x/webarena |
| [`benchmarks/osworld/`](benchmarks/osworld/) | OSWorld | github.com/xlang-ai/OSWorld |
| [`benchmarks/appworld/`](benchmarks/appworld/) | AppWorld | github.com/StonyBrookNLP/appworld |
| [`benchmarks/t-bench/`](benchmarks/t-bench/) | T-Bench | (tool-calling benchmark) |

---

## Inference Engines

| Engine | Backend | Best For | Quant |
|---|---|---|---|
| **vLLM** | OpenVINO / PyTorch | Multi-instance serving | INT8, INT4 |
| **llama.cpp** | GGML/GGUF + AVX-VNNI | Single-instance, fast startup | Q4_K_M, Q8_0 |
| **OpenVINO GenAI** | OpenVINO IR | Max throughput production | INT8, INT4 |

Start scripts: [`scripts/inference/`](scripts/inference/)

---

## Repository Structure

```
CWF_AgenticAI_wls/
├── docs/
│   └── index.html              # Full HTML test plan (main documentation)
├── README.md                   # This file
├── benchmarks/
│   ├── swe-bench/README.md     # SWE-bench quick start
│   ├── webarena/README.md      # WebArena quick start
│   ├── osworld/README.md       # OSWorld quick start
│   ├── appworld/README.md      # AppWorld quick start
│   └── t-bench/README.md       # T-Bench quick start
├── scripts/
│   ├── setup/
│   │   ├── setup_base.sh       # Base system prerequisites
│   │   ├── setup_swebench.sh   # SWE-bench install
│   │   ├── setup_webarena.sh   # WebArena install + web services
│   │   ├── setup_osworld.sh    # OSWorld install (KVM)
│   │   ├── setup_appworld.sh   # AppWorld install
│   │   └── setup_tbench.sh     # T-Bench install
│   └── inference/
│       ├── start_vllm.sh       # vLLM server (CWF-optimized)
│       └── start_llamacpp.sh   # llama.cpp server (AVX-VNNI)
├── configs/
│   ├── swebench.yaml           # SWE-bench run parameters
│   ├── webarena.yaml           # WebArena run parameters
│   ├── osworld.yaml            # OSWorld run parameters
│   ├── appworld.yaml           # AppWorld run parameters
│   └── tbench.yaml             # T-Bench run parameters
└── results/
    ├── .gitkeep
    └── README.md               # Results format and schema
```

---

## Quick Start

```bash
# 1. Base system setup (Docker, KVM, Python 3.11)
bash scripts/setup/setup_base.sh

# 2. Start LLM inference server (pick one)
bash scripts/inference/start_llamacpp.sh --model 8b --cores 64
bash scripts/inference/start_vllm.sh --model 8b --cores 64

# 3. Install and run a benchmark
bash scripts/setup/setup_appworld.sh    # lightest — start here
bash scripts/setup/setup_swebench.sh
bash scripts/setup/setup_webarena.sh
bash scripts/setup/setup_osworld.sh     # requires KVM
bash scripts/setup/setup_tbench.sh
```

**Recommended execution order (per test plan phases):**
1. AppWorld + T-Bench (Days 1–2) — lightest, validate full pipeline
2. SWE-bench (Days 3–5) — Docker-based, moderate complexity
3. WebArena (Days 6–8) — multi-container web services
4. OSWorld (Days 9–11) — heaviest, requires KVM
5. Full scaling characterization (Days 12–14) — EMON + power

---

## Scaling Study

### Phase 1: Single-Instance Core Scaling

| Inference Cores | Env Cores | Goal |
|---|---|---|
| 16 | 8 | Minimum viable baseline |
| 32 | 16 | Module-group boundary |
| 64 | 16 | Cross-module scaling |
| 96 | 32 | Approaching BW limits |
| 128 | 32 | Near-socket saturation |
| 192+ | 48 | Full platform |

### Phase 2: Multi-Instance Throughput

| Instances | Cores/Instance | Total Cores | KPI |
|---|---|---|---|
| 1 | 64+16 | 80 | Baseline |
| 2 | 64+16 | 160 | Linear check |
| 4 | 32+8 | 160 | Same cores, more instances |
| 8 | 16+8 | 192 | High parallelism |
| 16 | 12+6 | 288 | Maximum (≥288 cores) |

---

## KPIs & Metrics

| Category | Metric | Unit |
|---|---|---|
| LLM Inference | Decode tokens/sec | tok/s |
| LLM Inference | Time-to-first-token (TTFT) | ms |
| Throughput | Tasks completed per hour | tasks/hr |
| Efficiency | Tasks per watt-hour | tasks/Wh |
| Microarch | IPC, LLC MPKI, Mem BW % | EMON |
| SWE-bench | resolve_rate | % |
| WebArena | success_rate | % |
| OSWorld | success_rate | % |
| AppWorld | task_completion_rate | % |
| T-Bench | tool_accuracy | % |

---

## Results Format

See [`results/README.md`](results/README.md) for the expected output schema and directory layout.

---

## Documentation

📄 **[Full HTML Test Plan → docs/index.html](docs/index.html)**

The interactive test plan includes:
- Platform model (CWF architecture details)
- Benchmark deep-dive (setup, evaluation flow, resource requirements)
- Deployment architecture diagrams
- Scaling study design with projected throughput charts
- KPIs, EMON strategy, execution phase timeline
- Risks and mitigations
- Hardware/software prerequisites

---

*Intel Confidential | DPG PAIV SO | Clearwater Forest Agentic AI Workload Characterization — Test Plan v1.0*
