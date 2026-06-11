---
applyTo: "benchmarks/swe-bench/**"
---
# SWE-bench — Copilot Instructions

## Quick Facts
- **Splits**: lite (300 tasks), verified (500), full (2294)
- **Containers**: One Docker container per task — needs significant disk space
- **BKM max workers**: min(0.75 * nproc, 24) — avoid overwhelming Docker
- **LLM API**: llama.cpp or vLLM on port 8000

## Run Pattern
```bash
python3 scripts/inference/start_vllm.py --model 32b --cores 96
python3 benchmarks/swe-bench/run.py --split lite --max-workers 8
```

## Config (`config/workload_config.yaml`)
- `workload.default_split`: lite
- `workload.default_max_workers`: 8
- `workload.bkm_formula`: "min(int(0.75 * nproc), 24)"
- `telemetry.emon_warmup_s`: 60

## Output Dir Pattern
`results/swebench/swebench_{split}_{model}_{inf_cores}c_{timestamp}/`

## Key Notes
- Use `--split lite` for initial validation (30-60 min vs 10+ hours for full)
- Predictions saved to `predictions/{run_id}.jsonl` before evaluation
- Docker cleanup happens automatically — check disk space before full run
- Score = resolved_count / total_instances
