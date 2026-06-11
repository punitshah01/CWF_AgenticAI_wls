---
applyTo: "benchmarks/webarena/**"
---
# WebArena — Copilot Instructions

## Quick Facts
- **812 tasks** across shopping, reddit, gitlab, map, wikipedia domains
- **~14% success rate** observed with llama3:70b on CWF
- **LLM**: Ollama port 11434 (default), or llama.cpp/vLLM port 8000
- **Key env vars**: OPENAI_API_BASE, OPENAI_API_KEY, service endpoint URLs

## Run Pattern
```python
# EMON: 60s warmup → 180s collection
tm = TelemetryManager(emon_warmup_s=60, emon_duration_s=180, ...)
tm.start(session_name=run_id)
subprocess.run(eval_cmd, ...)   # WebArena evaluation
tm.stop(process_emon=True)
```

## Config (`config/workload_config.yaml`)
- `workload.default_model`: 8b | 32b | 70b
- `workload.default_start_idx` / `default_end_idx`: task range
- `telemetry.emon_warmup_s`: default 60
- `telemetry.emon_duration_s`: default 180

## Output Dir Pattern
`results/webarena/webarena_{model}_{inf_cores}c_{n_tasks}tasks_{timestamp}/`

## DO NOT
- Hardcode task indices — use --start-idx / --end-idx
- Start GitLab container — it crashes on CWF RHEL9/overlay2
