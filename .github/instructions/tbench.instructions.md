---
applyTo: "benchmarks/t-bench/**"
---
# T-Bench — Copilot Instructions

## Quick Facts
- Function-calling tasks: tool_selection, param_extraction, multi_step, error_recovery, workflow_completion
- Needs a **FastAPI mock server** on port 9000 (auto-started by runner)
- **LLM API**: llama.cpp or Ollama

## Run Pattern
```bash
# Mock server is started automatically by the runner
python3 benchmarks/t-bench/run.py --model 8b --categories tool_selection param_extraction
```

## Config (`config/workload_config.yaml`)
- `workload.default_categories`: all 5 categories
- `workload.mock_port`: 9000
- `workload.default_llm_port`: 8000

## Output Dir Pattern
`results/tbench/tbench_{model}_{inf_cores}c_{timestamp}/`

## Key Notes
- Runner auto-generates minimal mock_server.py if not present
- Use `--categories` to run subset — useful for debugging
- Score = correct_calls / total_calls per category
- FastAPI + uvicorn must be installed in the venv
