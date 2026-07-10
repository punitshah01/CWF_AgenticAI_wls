# Architecture — CWF Agentic AI Benchmarks

## Overview

This repository validates agentic AI workloads on **CWF (Clearwater Forest)** — Intel's Xeon
platform built on E-core Darkmont tiles.  Five state-of-the-art agentic benchmarks are
integrated into a unified harness that collects platform telemetry (EMON, RAPL, temperature)
alongside benchmark KPIs, enabling joint hardware/software performance analysis.

---

## Folder Structure

```
CWF_AgenticAI_wls/
│
├── benchmarks/                    # One sub-folder per benchmark
│   ├── appworld/
│   │   ├── build/                 # build.py + requirements.txt
│   │   ├── config/                # default_config.yaml, workload_config.yaml
│   │   ├── lib/                   # benchmark-internal helper modules (optional)
│   │   ├── run.py                 # Class-based runner (ExecutionContext → ... → Runner)
│   │   ├── run_appworld.py        # Thin CLI entry point that calls run.py's Runner
│   │   ├── setup.py               # Workload-specific dependency installer
│   │   └── README.md
│   ├── osworld/                   # (same structure)
│   ├── swe-bench/                 # (same structure)
│   ├── t-bench/                   # (same structure)
│   └── webarena/                  # (same structure)
│
├── common/                        # Shared Python utilities (the "common setup layer")
│   ├── cli_utils.py               # get_base_parser(), parse_config(), TeeOutput logging
│   ├── cpu_info.py                # CPUInfo: lscpu topology
│   ├── csv_writer.py              # write_csv_row()
│   ├── docker_utils.py            # pull_image(), run_container()
│   ├── git_provenance.py          # get_provenance_dict()
│   ├── json_results.py            # ResultsJsonWriter
│   ├── metadata.py                # build_metadata()
│   ├── os_info.py                 # OSInfo: kernel, BIOS, microcode
│   ├── platform_info.py           # detect_platform(): CWF/DMR/GNR/…
│   ├── run_generic.py             # run_cmd(), stream_output()
│   ├── setup_utils.py             # Shared setup.py helpers (Color/log/banner/run,
│   │                               #   pip_install, ensure_conda_env, setup markers, ...)
│   ├── system_info.py             # get_system_info()
│   ├── system_metadata.py         # get_system_metadata()
│   ├── tuneup_utils.py            # set_cpu_governor(), disable_aslr()
│   ├── config/                    # docker_config.yaml
│   └── telemetry/                 # EMON, RAPL, SSMON, PTAT collectors + TelemetryManager
│
├── configs/                       # Legacy root-level configs (now reference benchmarks/*/config/)
├── docs/                          # This folder
├── misc/                          # Standalone utility scripts (check_emon, collect_rapl, …)
├── results/                       # Run outputs (gitignored except README)
├── scripts/                       # Common (cross-benchmark) infrastructure setup
│   ├── setup.py                   # Installs shared infra: base pkgs, Docker, conda, EMON/SEP
│   └── inference/                 # llama.cpp / vLLM inference server start scripts
└── setup/                         # Lower-level, reusable system-setup building blocks
    ├── setup_docker.py            # Docker CE install (called by scripts/setup.py)
    ├── setup_emon.py              # Intel SEP/EMON install (called by scripts/setup.py)
    ├── setup_kernel_devel.py      # Kernel headers/devel packages (for perf/msr tools)
    ├── setup_platform.py          # CPU governor, ASLR, THP tuning
    └── setup_venv.py              # Python venv creation helper
```

---

## Shared Setup vs Workload-Specific Setup

The setup flow is split into two clear layers so that common functionality is written
**once** and workload setup only contains what is truly benchmark-specific:

1. **Shared / common setup** — run **once per machine**, before any benchmark:
   - `scripts/setup.py` installs base OS packages (numactl, hwloc, msr-tools, …), Docker,
     the base conda environment, git-lfs, common Python packages, and (optionally, via
     `--install-emon`) the Intel SEP/EMON telemetry stack (delegating to `setup/setup_emon.py`).
   - `common/setup_utils.py` provides the reusable Python helpers every benchmark's
     `setup.py` imports: colored `log()`/`banner()` output, `run()`/`run_capture()` shell
     execution, `pip_install()`, `ensure_conda_env()`, `require_python_version()`,
     `detect_os_family()`, and `write_setup_marker()`.
   - `common/telemetry/`, `common/system_metadata.py`, `common/cli_utils.py`, and
     `common/csv_writer.py` provide the shared runtime layer (telemetry collection,
     system/CPU/OS metadata capture, logging, and result output) used identically by
     every benchmark runner.

2. **Workload-specific setup** — each `benchmarks/<name>/setup.py` handles only what is
   unique to that benchmark: its Python package list, conda env creation (via the shared
   `ensure_conda_env()` helper), container/VM setup (e.g. OSWorld's KVM packages, WebArena's
   Docker images), task/data generation, benchmark repo cloning, and benchmark-specific
   validation (e.g. SWE-bench's gold-patch check). Workload setup scripts must **not**
   re-implement the shared helpers above — they import them from `common/setup_utils.py`.

Running order on a fresh machine:

```bash
python3 scripts/setup.py --install-emon      # once per machine
python3 benchmarks/<name>/setup.py           # once per benchmark
python3 benchmarks/<name>/run.py ...         # every run
```

---

## How `common/` Utilities Are Shared

Every benchmark runner imports from `common/` via the repo root on `sys.path`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from common.cli_utils import get_base_parser, parse_config
from common.metadata import build_metadata
```

Key contracts:

| Module | Primary export | Used by |
|--------|----------------|---------|
| `cli_utils` | `get_base_parser()`, `setup_tee_logging()` | All `run_<name>.py` files |
| `metadata` | `build_metadata(cfg, name)` | Alternate metadata-block builder (not currently used by run.py; available for future runners) |
| `json_results` | `ResultsJsonWriter` | All runners for `results.json` (the actual schema every runner emits) |
| `system_metadata` | `get_system_metadata()` | All runners for the `system` metadata block |
| `run_generic` | `run_cmd(cmd, retries=N)` | Runners needing subprocess retry |
| `tuneup_utils` | `set_cpu_governor()` | `setup/setup_platform.py` (Python callers) |
| `git_provenance` | `get_provenance_dict()` | Embedded in every result file |
| `docker_utils` | `pull_image()`, `run_container()` | Benchmarks using Docker evaluation |
| `setup_utils` | `run()`, `pip_install()`, `ensure_conda_env()`, `write_setup_marker()` | Every `benchmarks/<name>/setup.py` |
| `telemetry.manager` | `TelemetryManager` | All runners for EMON/RAPL/temperature |

---

## Result Format

Every benchmark writes its outputs to
`results/<name>/<name>_<config-signature>_<timestamp>/`, containing:

- `console_output.log` — full stdout+stderr, tee'd live via `common.cli_utils.setup_tee_logging()`
- `results.json` — structured metadata + results (schema below)
- `results.csv` — one row per run/task, appended via `common/csv_writer.write_csv_row()`
- `telemetry/` — raw EMON artifacts, `mpp.py` post-processed summaries, RAPL/temperature CSVs
  (present even when telemetry collection is skipped, so the folder shape stays predictable)
- benchmark-specific artifacts (e.g. SWE-bench `predictions/*.jsonl`, WebArena per-task logs)

### `results.json`
Written by the shared `common.json_results.ResultsJsonWriter` — identical
schema across all 5 benchmarks:
```json
{
  "run_id": "webarena_8b_96c_50tasks_20260610_120000",
  "rows": [
    {
      "system":    { "cpu_model": "...", "cpu_sockets": "1", "total_cores": "288", "...": "..." },
      "results":   { "score": "0.312", "tasks_completed": "254", "pkg_power_w": "185.0" },
      "emon":      { "...socket-view EMON metrics, empty {} if not collected...": 0 },
      "emon_core": { "...optional core-view EMON metrics...": 0 },
      "rapl":      { "pkg_w": 185.0, "dram_w": 42.1 }
    }
  ]
}
```
`system` vs `results` classification is fixed by `common.json_results._SYSTEM_KEYS`
so every benchmark's output can be parsed the same way. `common.metadata.build_metadata()`
is also available for a `{"metadata": {...}, "results": {...}}` shape if a future
runner prefers it, but the `ResultsJsonWriter` rows format above is what every
current runner emits.

### `results.csv`
One row per task or repetition, columns vary by benchmark.  Written via
`common/csv_writer.write_csv_row()`.

---

## How to Add a New Benchmark

1. **Create the folder:**
   ```
   benchmarks/<name>/
   ├── build/
   │   ├── build.py
   │   └── requirements.txt
   ├── config/
   │   ├── default_config.yaml     # must include: model, agent, max_steps,
   │   │                            #   timeout_seconds, output_dir, log_level
   │   └── workload_config.yaml    # workload-specific defaults (telemetry, dataset, ...)
   ├── run.py                      # ExecutionContext → ConfigValidator → WorkloadExecutor
   │                                #   → ResultsManager → <Name>Runner.run()
   ├── run_<name>.py                # Thin CLI entry point calling into run.py
   ├── setup.py                    # Workload-specific setup only (see below)
   └── README.md
   ```

2. **`setup.py` must:**
   - Import shared helpers from `common.setup_utils` (`log`, `banner`, `run`, `pip_install`,
     `ensure_conda_env`, `require_python_version`, `write_setup_marker`, …) instead of
     re-implementing them
   - Contain only workload-specific logic: package lists, container/VM setup, task data
     generation, benchmark repo cloning, benchmark-specific validation
   - Write a `.setup_complete` marker via `write_setup_marker()` so `run.py` can fail fast
     with an actionable error if setup hasn't been run

3. **`run.py` / `run_<name>.py` must:**
   - Call `common.cli_utils.get_base_parser()` for the base parser and
     `common.cli_utils.setup_tee_logging()` for `console_output.log`
   - Accept `--output-dir`, `--config`, `--collect-emon`, `--dry-run`, `--verbose`
   - Capture system metadata via `common.system_metadata.get_system_metadata()`
   - Start/stop telemetry via `common.telemetry.manager.TelemetryManager`
   - Produce `results.json` via `common.json_results.ResultsJsonWriter` (the
     `system` vs `results` field split is automatic) and append a row to
     `results.csv` via `common.csv_writer.write_csv_row()`
   - Register `SIGINT`/`SIGTERM` handlers that stop telemetry gracefully before exiting
   - Degrade gracefully (log a warning, continue) when optional telemetry, Docker services,
     or the LLM server are unavailable, rather than crashing the whole run

4. **Add a `configs/<name>.yaml`** stub referencing `benchmarks/<name>/config/default_config.yaml`

5. **Update `common/setup_utils.py`** only if you discover *new* logic that is generic
   across benchmarks — do not duplicate it into the new `setup.py`

6. **Update `docs/WORKLOAD_REGISTRY.md`** and add `benchmarks/<name>/README.md`

7. **Update `.github/workflows/ci.yml`** (if present) to include the new runner in the
   dry-run smoke test
