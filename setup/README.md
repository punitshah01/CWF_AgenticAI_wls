# Setup Scripts

This folder holds the lower-level, reusable building blocks that
`scripts/setup.py` (the shared/common setup entry point) calls into.
Application code should generally invoke `scripts/setup.py`, not these
scripts directly, unless re-running a single step.

| Script | Purpose |
|---|---|
| `setup_platform.py` | CPU governor, ASLR, THP tuning (performance baseline) |
| `setup_venv.py` | Python venv creation helper |
| `setup_docker.py` | Install Docker CE (Ubuntu/CentOS auto-detected) |
| `setup_emon.py` | Install Intel SEP/EMON, pyedp, and TMC telemetry client |
| `setup_kernel_devel.py` | Kernel headers/devel packages needed by perf/msr tools |
| `../scripts/setup.py` | Shared/common infra installer for all 5 benchmarks (base OS
|                        | packages, Docker, conda, common Python deps, optional EMON) |
| `../common/setup_utils.py` | Python helpers (`log`, `banner`, `run`, `pip_install`,
|                        | `ensure_conda_env`, `write_setup_marker`, ...) imported by every
|                        | `benchmarks/<name>/setup.py` — the shared setup *library*, as
|                        | opposed to the shared setup *script* above |

## Setup layers

1. **Shared/common setup (once per machine):** `scripts/setup.py` installs
   everything every benchmark needs regardless of which workload you run —
   base system packages, Docker, the base conda environment, common Python
   packages, and (with `--install-emon`) the EMON/SEP telemetry stack.
2. **Workload-specific setup (once per benchmark):** each
   `benchmarks/<name>/setup.py` installs only what that benchmark needs
   (its Python packages, container/VM setup, task data, benchmark repo
   clone) using the shared helpers in `common/setup_utils.py`.

## Quick setup order

```bash
# 1. Shared/common infra (Docker, conda, base packages) + EMON telemetry stack
python3 scripts/setup.py --install-emon

# 2. Per-benchmark setup (installs only what that benchmark needs)
python3 benchmarks/swe-bench/setup.py
python3 benchmarks/webarena/setup.py
python3 benchmarks/osworld/setup.py
python3 benchmarks/appworld/setup.py
python3 benchmarks/t-bench/setup.py

# 3. Verify EMON before each run
python3 misc/check_emon_setup.py
```

## Offline / air-gapped setup

```python
# On internet-connected machine — pull all images + files once:
python3 scripts/prefetch_assets.py start-registry
python3 scripts/prefetch_assets.py pull
python3 scripts/prefetch_assets.py push --registry localhost:5000

# On SUT (no internet):
python3 scripts/setup.py --registry localhost:5000 --pip-cache-dir /data/pip-cache
```

