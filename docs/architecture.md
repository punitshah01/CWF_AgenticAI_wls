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
│   │   ├── build/                 # build.sh + requirements.txt
│   │   ├── config/                # default_config.yaml
│   │   ├── run.py                 # Legacy runner (benchmark-specific CLI)
│   │   ├── run_appworld.py        # Canonical runner (uses common/cli_utils)
│   │   ├── run_appworld.sh        # Shell entry point (activates venv, tees log)
│   │   └── setup.py               # Self-contained dependency installer
│   ├── osworld/                   # (same structure)
│   ├── swe-bench/                 # (same structure)
│   ├── t-bench/                   # (same structure)
│   └── webarena/                  # (same structure)
│
├── common/                        # Shared Python utilities
│   ├── cli_utils.py               # get_base_parser(), parse_config()
│   ├── cpu_info.py                # CPUInfo: lscpu topology
│   ├── csv_writer.py              # write_csv_row()
│   ├── docker_utils.py            # pull_image(), run_container()
│   ├── git_provenance.py          # get_provenance_dict()
│   ├── json_results.py            # ResultsJsonWriter
│   ├── metadata.py                # build_metadata()
│   ├── os_info.py                 # OSInfo: kernel, BIOS, microcode
│   ├── platform_info.py           # detect_platform(): CWF/DMR/GNR/…
│   ├── run_generic.py             # run_cmd(), stream_output()
│   ├── system_info.py             # get_system_info()
│   ├── system_metadata.py         # get_system_metadata()
│   ├── tuneup_utils.py            # set_cpu_governor(), disable_aslr()
│   ├── config/                    # docker_config.yaml
│   └── telemetry/                 # EMON, RAPL, SSMON, PTAT collectors
│
├── configs/                       # Legacy root-level configs (now reference benchmarks/*/config/)
├── docs/                          # This folder
├── misc/                          # Standalone utility scripts (check_emon, collect_rapl, …)
├── results/                       # Run outputs (gitignored except README)
├── scripts/                       # Common setup + inference server scripts
│   ├── setup.py                   # Common infra: conda, Docker, EMON
│   └── inference/                 # llama.cpp / vLLM start scripts
└── setup/                         # System-level setup scripts
    ├── setup_docker.py
    ├── setup_emon.py
    ├── setup_kernel_devel.py
    ├── setup_platform.sh          # CPU governor, ASLR, THP tuning
    └── setup_venv.sh              # Python venv creation
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
| `cli_utils` | `get_base_parser()` | All `run_<name>.py` files |
| `metadata` | `build_metadata(cfg, name)` | All runners for result JSON |
| `run_generic` | `run_cmd(cmd, retries=N)` | Runners needing subprocess retry |
| `tuneup_utils` | `set_cpu_governor()` | `setup/setup_platform.sh` (Python callers) |
| `git_provenance` | `get_provenance_dict()` | Embedded in every result file |
| `docker_utils` | `pull_image()`, `run_container()` | Benchmarks using Docker evaluation |

---

## Result Format

Every benchmark produces two output files in `--output-dir`:

### `results.json`
```json
{
  "metadata": {
    "benchmark": "webarena",
    "timestamp": "2026-06-10T12:00:00Z",
    "provenance": { "sha": "abc1234", "branch": "main", "repo_url": "..." },
    "system": { "cpu_model": "...", "sockets": 1, "cores": 288, ... },
    "config": { ... }
  },
  "results": {
    "score": 0.312,
    "tasks_passed": 254,
    "tasks_total": 812
  }
}
```

### `results.csv`
One row per task or repetition, columns vary by benchmark.  Written via
`common/csv_writer.write_csv_row()`.

### `run.log`
Full stdout + stderr, written by `run_<name>.sh` via `tee`.

---

## How to Add a New Benchmark

1. **Create the folder:**
   ```
   benchmarks/<name>/
   ├── build/
   │   ├── build.sh
   │   └── requirements.txt
   ├── config/
   │   └── default_config.yaml     # must include: model, agent, max_steps,
   │                                #   timeout_seconds, output_dir, log_level
   ├── run.py                       # benchmark-specific implementation
   ├── run_<name>.py               # canonical runner using common/cli_utils
   ├── run_<name>.sh               # shell entry point
   ├── setup.py                    # self-contained dependency installer
   └── README.md
   ```

2. **`run_<name>.py` must:**
   - Call `common.cli_utils.get_base_parser()` for the base parser
   - Accept `--output-dir`, `--config`, `--iterations`, `--dry-run`, `--verbose`
   - Produce a result JSON with a `metadata` block from `common.metadata.build_metadata()`

3. **`run_<name>.sh` must:**
   - Start with `#!/bin/bash` and `set -euo pipefail`
   - Activate venv if present
   - Tee stdout+stderr to `$output_dir/run.log`

4. **Add a `configs/<name>.yaml`** stub referencing `benchmarks/<name>/config/default_config.yaml`

5. **Update `common/__init__.py`** if you add new shared utilities

6. **Update `.github/workflows/ci.yml`** to include the new runner in the dry-run smoke test
