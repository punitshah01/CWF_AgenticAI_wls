---
applyTo: "benchmarks/appworld/**"
---
# AppWorld — Copilot Instructions

## Quick Facts
- **Requires Python 3.11** (not 3.9 system Python)
- **Datasets**: dev (small), test_normal, test_challenge
- **Agent**: simplified_function_calling_agent (default)
- **LLM API**: llama.cpp/vLLM on port 8000 (not Ollama)

## Run Pattern
```bash
# Server must be started before runner
python3 scripts/inference/start_llamacpp.py --model 8b --cores 64

# Then run
python3 benchmarks/appworld/run.py --model 8b --dataset dev
```

## Config (`config/workload_config.yaml`)
- `workload.default_dataset`: dev | test_normal | test_challenge
- `workload.default_agent`: simplified_function_calling_agent
- `workload.default_instances`: 1 (can parallelize)
- `telemetry.collect_emon`: false by default (use --collect-emon to enable)

## Output Dir Pattern
`results/appworld/appworld_{dataset}_{model}_{inf_cores}c_{timestamp}/`

## Key Notes
- `appworld run auto` → runs agent on dataset
- `appworld evaluate` → scores predictions against ground truth
- Use `--num-instances` for parallel agent workers (limited by RAM)
