# CWF Agentic AI Workloads — Copilot Instructions

## Repo Purpose
Performance characterization of **agentic AI workloads** on Intel CWF (Clearwater Forest).
Five benchmarks: **WebArena, AppWorld, OSWorld, SWE-bench, T-Bench**.
Each is a closed-loop LLM agent evaluated on real tasks (web, OS, code, apps, tools).

## Architecture Pattern (mirrors pnpwls)
- `benchmarks/{workload}/run_{workload}.py` — main runner (class-based)
- `benchmarks/{workload}/setup_{workload}.py` — one-time setup
- `benchmarks/{workload}/config/workload_config.yaml` — per-workload defaults
- `common/` — shared CPU info, OS info, telemetry, CSV/JSON writers
- `common/telemetry/` — EMON (EDP), RAPL, SSMON/PTAT, TelemetryManager

## Key Conventions
1. **Runner pattern**: `ExecutionContext` → `ConfigValidator` → `WorkloadExecutor` → `ResultsManager` → `{Name}Runner.run()`
2. **TeeOutput**: All stdout/stderr goes to both console AND `console_output.log` simultaneously
3. **Signal handling**: `SIGINT`/`SIGTERM` → `cleanup_on_exit()` → stop telemetry + LLM server gracefully
4. **Output dir**: `results/{workload}/{workload}_{model}_{config_sig}_{timestamp}/`
5. **Per-workload YAML**: Load defaults from `config/workload_config.yaml`; CLI args override YAML
6. **EMON**: `emon -collect-edp` start, `emon -stop` stop, `mpp.py` post-process
7. **Results**: Always write both `results.csv` (append row) AND `results.json` (structured)

## Platform: CWF (Clearwater Forest)
- Architecture: Darkmont E-cores, no SMT (threads_per_core=1), up to 288 cores
- CPU family: 19, single NUMA domain (or up to 4 CBBs each with own L3)
- OS: CentOS Stream 9, Python 3.9 system / 3.11 venv
- EMON: /opt/intel/sep 5.58 beta, EDP at /opt/intel/sep/config/edp/
- LLM: Ollama (port 11434) or llama.cpp/vLLM (port 8000)

## Telemetry Quick Reference
```python
tm = TelemetryManager(
    output_dir=str(out_dir / "telemetry"),
    platform="clearwaterforest",
    collect_emon=args.collect_emon,
    collect_rapl=True,
    emon_warmup_s=60,
    emon_duration_s=180,
)
tm.start(session_name=run_id)
# ... run workload ...
tm.stop(process_emon=args.collect_emon, sockets=1)
```

## DO NOT
- Hardcode core counts — use `CPUInfo().get_total_cores()`
- Hardcode NUMA topology — use `CPUInfo().get_numa_nodes()`
- Use `killpg()` to stop EMON — use `emon -stop`
- Use `-C "event-list"` for EMON — use `emon -collect-edp`
- Create new files unless necessary — edit existing ones

## Workload-Specific Notes
- **WebArena**: 812 tasks, ~14% success on CWF 70b, 60s warmup before EMON
- **AppWorld**: Needs Python 3.11; datasets: dev/test_normal/test_challenge
- **OSWorld**: QEMU/KVM VMs, each ~8GB RAM; screenshot or accessibility_tree obs
- **SWE-bench**: Docker containers per task; BKM workers = min(0.75*nproc, 24)
- **T-Bench**: Function-calling tasks; needs FastAPI mock server on port 9000
