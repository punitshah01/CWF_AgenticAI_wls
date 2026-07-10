# Workload Registry

This repo contains 5 agentic AI benchmark runners for Intel CWF (Clearwater Forest) platform characterization.

## Workloads

| Workload | Directory | Entry Point | KPI | Status |
|---|---|---|---|---|
| WebArena | `benchmarks/webarena/` | `run.py` | Success Rate (%) | ✅ Active |
| AppWorld | `benchmarks/appworld/` | `run.py` | Score / Pass Rate | ✅ Active |
| OSWorld | `benchmarks/osworld/` | `run.py` | Tasks Passed / Total | ✅ Active |
| SWE-bench | `benchmarks/swe-bench/` | `run.py` | Resolved Count | ✅ Active |
| T-Bench | `benchmarks/t-bench/` | `run.py` | Category Accuracy | ✅ Active |

## Workload Details

### WebArena
- **Type**: Web agent (LLM + Playwright browser)
- **Dataset**: 812 tasks across shopping, reddit, gitlab, map, wikipedia
- **LLM**: Ollama llama3:8b/70b (port 11434) or llama.cpp/vLLM (port 8000)
- **CWF BKM**: 96 inference cores, 48 env cores, 60s EMON warmup, 180s EMON collection
- **Observed**: ~14% success rate with llama3:70b on CWF
- **Config**: `benchmarks/webarena/config/workload_config.yaml`

### AppWorld
- **Type**: Application agent (LLM + UI task automation)
- **Datasets**: dev (quick validation), test_normal, test_challenge
- **LLM**: llama.cpp/vLLM on port 8000 (Python 3.11 required)
- **CWF BKM**: 64 inference cores, Python 3.11 venv
- **Config**: `benchmarks/appworld/config/workload_config.yaml`

### OSWorld
- **Type**: OS desktop task agent (LLM + QEMU/KVM VMs)
- **Observation types**: screenshot (default), accessibility_tree
- **LLM**: vLLM on port 8000; each VM uses ~8 GB RAM
- **CWF BKM**: 96 inference cores, 4 parallel VMs, 120s EMON warmup (VM boot)
- **Config**: `benchmarks/osworld/config/workload_config.yaml`

### SWE-bench
- **Type**: Software engineering (LLM + Docker containers for eval)
- **Splits**: lite (300 tasks), verified (500), full (2294)
- **LLM**: llama.cpp or vLLM on port 8000
- **CWF BKM**: max_workers = min(int(0.75 * nproc), 24) ≈ 8 for most runs
- **Config**: `benchmarks/swe-bench/config/workload_config.yaml`

### T-Bench
- **Type**: Function-calling evaluation (LLM + FastAPI mock server)
- **Categories**: tool_selection, param_extraction, multi_step, error_recovery, workflow_completion
- **LLM**: Ollama or llama.cpp on port 8000/11434
- **CWF BKM**: 64 inference cores, mock server auto-started on port 9000
- **Config**: `benchmarks/t-bench/config/workload_config.yaml`

---

## Quick Start

```bash
# 1. Setup (one-time)
python3 scripts/setup.py --install-emon      # shared/common setup (all workloads)
python3 benchmarks/webarena/setup.py         # workload-specific setup

# 2. Run with telemetry
python3 benchmarks/webarena/run.py \
    --model 70b \
    --inference-cores 96 \
    --collect-emon \
    --emon-warmup 60 \
    --start-idx 0 \
    --end-idx 50

# 3. Results
ls results/webarena/
# webarena_70b_96c_50tasks_20260611_143022/
#   console_output.log
#   results.csv
#   results.json
#   telemetry/
```

## Output Structure

```
results/
└── {workload}/
    └── {workload}_{model}_{cores}c_{config}_{timestamp}/
        ├── console_output.log          # All stdout/stderr (tee'd)
        ├── results.csv                 # Appended summary row
        ├── results.json                # {run_id, rows: [{system, results, emon, emon_core, rapl}]}
                                          #   (see results/README.md for the full schema)
        └── telemetry/
            ├── emon_{run_id}.txt        # Raw EMON data
            ├── __mpp_socket_view_summary.csv
            ├── __mpp_system_view_summary.csv
            └── rapl_summary.csv
```

## Telemetry

All runners use the shared `TelemetryManager` from `common/telemetry/`:

| Collector | Type | Default | Notes |
|---|---|---|---|
| EMON | `emon -collect-edp` | Disabled | Enable with `--collect-emon` |
| RAPL | `/sys/class/powercap/` | Enabled | Full-run power baseline |
| SSMON/PTAT | Temperature | Disabled | Enable with `--collect-temp` |

See `common/telemetry/telemetry_config.yaml` for global telemetry settings.

## Adding a New Workload

This registry currently lists 5 workloads, but the repo is designed so a
6th (or Nth) workload requires minimal duplication:

1. Run shared/common setup once: `python3 scripts/setup.py --install-emon`.
2. Create `benchmarks/<name>/` following the layout and conventions in
   `docs/architecture.md#how-to-add-a-new-benchmark` (setup.py built on
   `common/setup_utils.py`, run.py built on `common/cli_utils`,
   `common/telemetry`, `common/system_metadata`, and
   `common/json_results.ResultsJsonWriter`).
3. Add a row to the **Workloads** table above and a **Workload Details**
   section describing its KPI, LLM port, and CWF BKM core split.
4. Add `benchmarks/<name>/README.md` documenting run/setup instructions.
