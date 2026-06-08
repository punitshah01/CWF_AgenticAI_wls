# Setup Scripts

| Script | Purpose |
|---|---|
| `setup_emon.py` | Install Intel SEP/EMON, pyedp, and TMC telemetry client |
| `setup_docker.py` | Install Docker CE (Ubuntu/CentOS auto-detected) |
| `../scripts/setup.py` | Unified Python installer for all 5 benchmarks |

## Quick setup order

```python
# 1. Base system (Docker, KVM, Conda)
python3 scripts/setup/setup_base.py

# 2. EMON (optional but recommended for performance characterization)
python3 setup/setup_emon.py

# 3. All benchmark Python deps
python3 scripts/setup.py

# 4. Per-benchmark setup (includes Docker image pull + post-install)
python3 benchmarks/swe-bench/setup.py
python3 benchmarks/webarena/setup.py
python3 benchmarks/osworld/setup.py
python3 benchmarks/appworld/setup.py
python3 benchmarks/t-bench/setup.py

# 5. Verify EMON before each run
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
