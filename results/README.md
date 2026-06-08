# Results Directory

This directory holds all benchmark output collected on CWF.  
Subdirectories are created automatically by each benchmark's run script.

---

## Directory Layout

```
results/
├── swebench/
│   ├── <run_id>/
│   │   ├── results.json            # per-task pass/fail
│   │   ├── report.json             # aggregate stats (resolve_rate, timing)
│   │   └── logs/                   # per-task Docker logs (optional)
│   └── summary.csv                 # multi-run comparison
│
├── webarena/
│   ├── <run_id>/
│   │   ├── results_cwf/            # raw WebArena output
│   │   │   ├── result.json         # per-task success/fail
│   │   │   └── screenshots/        # (optional) browser screenshots
│   │   └── metrics.json            # tokens/task, latency, power
│   └── summary.csv
│
├── osworld/
│   ├── <run_id>/
│   │   ├── result.json             # per-task per-domain success
│   │   ├── screenshots/            # VM action screenshots
│   │   └── metrics.json            # parallel env metrics
│   └── summary.csv
│
├── appworld/
│   ├── <run_id>/
│   │   ├── predictions.jsonl       # agent responses per task
│   │   ├── evaluation.json         # TCR, SGC scores
│   │   └── traces/                 # API call traces (optional)
│   └── summary.csv
│
├── tbench/
│   ├── <run_id>/
│   │   ├── tbench_results.json     # per-task tool accuracy
│   │   └── metrics.json
│   └── summary.csv
│
└── platform/
    ├── emon/                       # EMON raw .csv exports
    │   └── <run_id>_emon.csv
    ├── power/                      # RAPL measurements
    │   └── <run_id>_rapl.csv
    └── topology/
        └── lscpu_numactl.txt       # captured at run start
```

---

## Metrics Schema

### Per-Run `metrics.json`

```json
{
  "run_id": "cwf_baseline_20260608",
  "platform": {
    "codename": "CWF",
    "cpu_model": "Clearwater Forest",
    "total_cores": 288,
    "inference_cores": 64,
    "env_cores": 32,
    "memory_gb": 256
  },
  "llm": {
    "model": "Llama-3.1-8B-Instruct",
    "engine": "llama.cpp",
    "quantization": "Q4_K_M",
    "decode_tok_per_s": 22.5,
    "prefill_tok_per_s": 180.0,
    "ttft_ms": 450
  },
  "benchmark": {
    "name": "appworld",
    "dataset": "test_normal",
    "num_tasks": 750,
    "completed_tasks": 187,
    "task_completion_rate_pct": 24.9,
    "avg_task_latency_s": 45.2,
    "total_runtime_s": 33900,
    "tasks_per_hour": 19.8
  },
  "efficiency": {
    "avg_pkg_power_w": 185.0,
    "tasks_per_wh": 0.107,
    "tokens_per_watt": 0.122
  }
}
```

### `summary.csv` columns

| Column | Description |
|---|---|
| `run_id` | Unique run identifier |
| `benchmark` | Benchmark name |
| `date` | ISO timestamp |
| `model` | LLM model name |
| `quant` | Quantization (Q4_K_M etc.) |
| `inference_cores` | Cores allocated to LLM |
| `env_cores` | Cores for environment |
| `num_instances` | Parallel agent instances |
| `primary_kpi` | Benchmark's main metric (%) |
| `decode_tok_s` | LLM decode throughput |
| `tasks_per_hour` | Aggregate throughput |
| `avg_pkg_power_w` | Platform power draw |
| `tasks_per_wh` | Efficiency metric |

---

## Naming Convention

Run IDs follow: `<benchmark>_<model_size>_<cores>c_<instances>inst_<date>`

Examples:
- `appworld_8b_64c_1inst_20260608`
- `swebench_32b_96c_4workers_20260610`
- `osworld_32b_128c_8envs_20260612`

---

*Results are Intel Confidential. Do not push raw EMON or power data to public repos.*
