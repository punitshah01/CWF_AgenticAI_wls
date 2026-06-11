# SWE-bench

## Overview
Evaluates LLM agents on resolving real GitHub issues (2,294 total). Given a repository and a failing test, the agent must write a patch that fixes the issue. Evaluation uses Docker containers with the original test suite per task. Primary KPI: `resolve_rate` (% issues fully resolved).

Upstream: https://github.com/princeton-nlp/SWE-bench

---

## Prerequisites

| Item | Requirement |
|---|---|
| OS | CentOS Stream 9 / RHEL 9 (x86_64) |
| Python | 3.10+ |
| Docker CE | Running; 120 GB free disk |
| RAM | 16 GB+ |
| Disk | ~120 GB (Docker evaluation images) |
| Network | First run only (Docker Hub image pulls) |

---

## Setup

```bash
python3 benchmarks/swe-bench/setup.py
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--conda-env` | `swebench` | Conda environment name |
| `--python-version` | `3.10` | Python version for conda env |
| `--skip-validate` | off | Skip gold-patch validation |
| `--dry-run` | off | Print commands without executing |

**Expected output on success:**
```
[SUCCESS] SWE-bench setup complete
```

A `.setup_complete` marker is written to `benchmarks/swe-bench/` on success.

---

## Running

```bash
python3 benchmarks/swe-bench/run.py --model 32b --split lite --max-workers 8
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--model` | `32b` | LLM preset: `8b`, `32b`, `70b` |
| `--inference-cores` | `96` | CPU cores for LLM inference |
| `--env-cores` | `32` | CPU cores for Docker evaluation |
| `--split` | `lite` | `lite` (300), `verified` (500), `full` (2294) |
| `--max-workers` | `8` | Parallel Docker evaluation workers |
| `--llm-port` | `8000` | LLM API port |
| `--collect-emon` | off | Enable EMON telemetry |
| `--collect-rapl` | on | Enable RAPL power monitoring |
| `--dry-run` | off | Print config without running |

**BKM for max-workers on CWF:** `min(0.75 * nproc, 24)`

**Results saved to:** `results/swebench/swebench_{model}_{split}_{timestamp}/`

---

## Error Reference

| Error Message | Cause | Fix |
|---|---|---|
| `Setup not complete. Run setup.py first` | `.setup_complete` marker missing | Run `python3 benchmarks/swe-bench/setup.py` |
| `Docker disk space insufficient` | Less than 120 GB free | Free disk space or point Docker to larger volume |
| `docker pull rate limited` | Docker Hub rate limit | Log in: `docker login` |
| `swebench not found` | Package not installed | Re-run `setup.py` |

---

## Troubleshooting

**Check Docker disk space:**
```bash
df -h /var/lib/docker
docker system df
```

**Clean up evaluation containers:**
```bash
docker ps -a | grep swe | awk '{print $1}' | xargs docker rm -f
```

**Expected scores:** 5–25% resolve_rate depending on model and split.

---

## Results

Output directory: `results/swebench/swebench_{model}_{split}_{timestamp}/`

| File | Contents |
|---|---|
| `results.csv` | One row per run: resolve_rate, num_resolved, num_total |
| `results.json` | Structured JSON with system metadata |
| `console_output.log` | Full stdout/stderr |
| `telemetry/` | EMON EDP, RAPL samples |

**KPIs:** `resolve_rate` (primary), `tasks_per_hour`, `pkg_power_w`, `dram_power_w`
