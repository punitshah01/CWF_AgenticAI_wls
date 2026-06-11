---
applyTo: "benchmarks/osworld/**"
---
# OSWorld — Copilot Instructions

## Quick Facts
- Runs **QEMU/KVM VMs** for desktop automation tasks (~8 GB RAM per VM)
- Observation types: `screenshot` (default) or `accessibility_tree`
- **LLM API**: vLLM on port 8000 — must be started before runner
- Max parallel VMs limited by: total_RAM / 8GB

## Run Pattern
```bash
python3 scripts/inference/start_vllm.py --model 32b --cores 96
python3 benchmarks/osworld/run.py --model 32b --num-envs 4
```

## Config (`config/workload_config.yaml`)
- `workload.default_num_envs`: 4
- `workload.default_obs_type`: screenshot
- `workload.default_max_steps`: 15
- `telemetry.emon_warmup_s`: 120 (VM boot takes ~60s)

## Output Dir Pattern
`results/osworld/osworld_{model}_{inf_cores}c_{num_envs}envs_{timestamp}/`

## Key Notes
- KVM must be enabled: `lsmod | grep kvm`
- Each VM uses ~8 GB RAM — check available RAM before running
- `--obs-type accessibility_tree` is faster but less reliable than screenshot
- Score = tasks_passed / tasks_total
