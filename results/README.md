# Results Directory

This directory holds all benchmark output collected on CWF.
Subdirectories are created automatically by each benchmark's `run.py`,
using the standardized layout below across all 5 workloads (SWE-bench,
WebArena, OSWorld, AppWorld, T-Bench) so the same tooling — and, in the
future, a dashboard — can consume any benchmark's output uniformly.

---

## Directory Layout

Every run creates one folder per invocation:

```
results/<workload>/<workload>_<config-signature>_<timestamp>/
```

e.g. `results/webarena/webarena_70b_96c_50tasks_20260611_143022/`

Inside every run folder:

```
<run_id>/
├── console_output.log     # Full stdout+stderr, tee'd live (common.cli_utils.setup_tee_logging)
├── results.csv            # One appended row per run (common.csv_writer.write_csv_row)
├── results.json           # Structured {metadata: {..., system, provenance, config}, results: {...}}
└── telemetry/             # Always present, even if telemetry was skipped/unavailable
    ├── emon_<run_id>.txt          # Raw EMON export (only if --collect-emon)
    ├── __mpp_socket_view_summary.csv
    ├── __mpp_system_view_summary.csv
    └── rapl_summary.csv           # RAPL power summary (collected by default)
```

Benchmark-specific artifacts are written alongside these standard files
(they never replace them), e.g.:

- **SWE-bench**: `predictions/<run_id>.jsonl`
- **WebArena**: per-task WebArena result JSON copied from the upstream harness
- **OSWorld**: per-task VM screenshots (if `--obs-type screenshot`)
- **AppWorld**: `appworld evaluate` output copied into the run folder

Cross-run rollups (`platform/` telemetry captures shared across runs, and
per-workload `summary.csv` files aggregating multiple `results.csv` rows)
may also live here.

---

## `results.json` Schema

Every benchmark writes `results.json` via the shared
`common.json_results.ResultsJsonWriter`, so all 5 workloads share the same
top-level schema and can be parsed identically by tooling (and, in the
future, a dashboard):

```json
{
  "run_id": "appworld_dev_8b_64c_20260710_080719",
  "rows": [
    {
      "system": {
        "run_id": "appworld_dev_8b_64c_20260710_080719",
        "hostname": "cwf-node-01",
        "platform": "CWF",
        "cpu_model": "Intel(R) Xeon(R) ...",
        "total_cores": "288",
        "numa_nodes": "1",
        "memory_total_gb": "256",
        "kernel": "5.15.0-...",
        "os_release": "..."
      },
      "results": {
        "task_completion_rate": "24.9",
        "sgc_score": "0.107",
        "tasks_completed": "187",
        "pkg_power_w": "185.0",
        "dram_power_w": "42.1"
      },
      "emon": { "...socket-view EMON metrics, only if --collect-emon...": 0 },
      "emon_core": { "...core-view EMON metrics, optional...": 0 },
      "rapl": { "pkg_w": 185.0, "dram_w": 42.1 }
    }
  ]
}
```

- Every field in `common/system_metadata.get_system_metadata()`'s output is
  classified into either `system` (CPU/OS/platform metadata) or `results`
  (benchmark KPIs) by `common.json_results.ResultsJsonWriter` — this split
  is fixed and identical across all benchmarks.
- `emon` / `emon_core` are empty dicts (not omitted) when EMON collection
  was skipped or unavailable, so consumers can always look up the key.
- `rapl` is populated from `TelemetryManager.rapl_mean` (collected by
  default; empty dict if RAPL is unavailable on the platform).
- `run.py` also calls `common.git_provenance.get_provenance_dict()` and
  `common.metadata.build_metadata()` is available for benchmarks/tooling
  that prefer a `{"metadata": {...}, "results": {...}}` shape, but the
  `ResultsJsonWriter` rows format above is what every current runner emits.

## `results.csv` columns

Each benchmark's `results.csv` mirrors its own KPI set, but always
includes at least: `run_id`, `hostname`, `platform`, `total_cores`, the
benchmark's KPI columns, `pkg_power_w`, and `dram_power_w`. New columns
should be appended, never reordered/removed, to keep historical CSVs
parseable (enforced by `common.csv_writer.write_csv_row()`, which only
rewrites the header when the column count changes).

---

## Naming Convention

Run IDs follow `<benchmark>_<params>_<timestamp>`, matching each
benchmark's `config/workload_config.yaml` (see
`docs/WORKLOAD_REGISTRY.md` for the exact pattern per workload), e.g.:

- `appworld_dev_8b_64c_20260710_080719`
- `swebench_lite_32b_96c_20260710_080719`
- `osworld_32b_96c_4envs_20260710_080719`

---

*Results are Intel Confidential. Do not push raw EMON or power data to public repos.*

