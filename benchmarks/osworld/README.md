# OSWorld

## Overview
Evaluates multimodal agents on 369 GUI automation tasks across real desktop applications (LibreOffice Calc/Writer/Impress, Chrome, Terminal, VSCode, GIMP, VLC, OS tasks). Each task runs inside a QEMU/KVM Ubuntu VM. Primary KPI: `success_rate` (% tasks where agent achieves the correct final state).

Upstream: https://github.com/xlang-ai/OSWorld

---

## Prerequisites

| Item | Requirement |
|---|---|
| OS | CentOS Stream 9 / RHEL 9 (x86_64) |
| Python | 3.10+ |
| KVM/VT-x | BIOS VT-x enabled; `egrep -c '(vmx|svm)' /proc/cpuinfo` > 0 |
| Docker CE | Running (`docker ps` works) |
| RAM | 32 GB+ (8 GB per VM instance) |
| Disk | ~100 GB (VM images) |
| Network | First run only |

---

## Setup

```bash
python3 benchmarks/osworld/setup.py
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--conda-env` | `osworld` | Conda environment name |
| `--python-version` | `3.10` | Python version for conda env |
| `--skip-kvm` | off | Skip KVM check and kernel package install |
| `--dry-run` | off | Print commands without executing |

**Expected output on success:**
```
[SUCCESS] OSWorld setup complete
```

A `.setup_complete` marker is written to `benchmarks/osworld/` on success.

---

## Running

```bash
python3 benchmarks/osworld/run.py --model 32b --num-envs 4 --obs-type screenshot
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--model` | `32b` | LLM preset: `8b`, `32b`, `70b` |
| `--inference-cores` | `96` | CPU cores for LLM inference |
| `--env-cores` | `64` | CPU cores for QEMU VMs |
| `--num-envs` | `4` | Parallel VM instances (8 GB RAM each) |
| `--obs-type` | `screenshot` | `screenshot` or `accessibility_tree` |
| `--max-steps` | `15` | Max actions per task |
| `--llm-port` | `8000` | LLM API port |
| `--collect-emon` | off | Enable EMON telemetry |
| `--collect-rapl` | on | Enable RAPL power monitoring |
| `--dry-run` | off | Print config without running |

**Results saved to:** `results/osworld/osworld_{model}_{numenvs}_{timestamp}/`

---

## Error Reference

| Error Message | Cause | Fix |
|---|---|---|
| `Setup not complete. Run setup.py first` | `.setup_complete` marker missing | Run `python3 benchmarks/osworld/setup.py` |
| `KVM flags NOT found` | VT-x disabled in BIOS | Enable VT-x/AMD-V in BIOS |
| `docker: permission denied` | Docker daemon not running | `systemctl start docker` |
| `Out of memory` | Too many VMs | Reduce `--num-envs` |

---

## Troubleshooting

**Check KVM availability:**
```bash
egrep -c '(vmx|svm)' /proc/cpuinfo   # must be > 0
ls /dev/kvm                           # must exist
```

**Clean up stale containers:**
```bash
docker stop $(docker ps -q) && docker rm $(docker ps -a -q)
```

**Expected scores:** 15–25% success_rate with 32B model.

---

## Results

Output directory: `results/osworld/osworld_{model}_{numenvs}_{timestamp}/`

| File | Contents |
|---|---|
| `results.csv` | One row per run: success_rate, num_success, per-domain breakdown |
| `results.json` | Structured JSON with system metadata |
| `console_output.log` | Full stdout/stderr |
| `telemetry/` | EMON EDP, RAPL samples |

**KPIs:** `success_rate` (primary), `tasks_per_hour`, `pkg_power_w`, `dram_power_w`
