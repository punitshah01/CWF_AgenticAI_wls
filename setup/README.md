# Setup Scripts

| Script | Purpose |
|---|---|
| `setup_emon.sh` | Install Intel SEP/EMON, pyedp, and TMC telemetry client |
| `setup_docker.sh` | Install Docker CE (Ubuntu/CentOS auto-detected) |
| `../scripts/setup/setup_base.sh` | Full base system setup (conda, KVM, git-lfs) |
| `../scripts/setup.py` | Unified Python installer for all 5 benchmarks |

## Quick setup order

```bash
# 1. Base system (Docker, KVM, Conda)
bash scripts/setup/setup_base.sh

# 2. EMON (optional but recommended for performance characterization)
bash setup/setup_emon.sh

# 3. All benchmark Python deps
python3 scripts/setup.py

# 4. Verify EMON before each run
collect_emon=$(bash misc/check_emon_setup.sh)
```
