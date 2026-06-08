# OSWorld — Quick Start

> **xlang-ai | NeurIPS 2024 | 369 tasks across real desktop GUIs**  
> Tests agents that interact with full Linux/Windows VMs via screenshots and accessibility trees.

---

## Overview

| Property | Value |
|---|---|
| Upstream | github.com/xlang-ai/OSWorld |
| Paper | arxiv.org/abs/2404.07972 |
| Tasks | 369 (LibreOffice, Chrome, Terminal, VSCode, GIMP, VLC, OS) |
| Environment | QEMU/KVM VMs launched via Docker+KVM |
| Primary KPI | `success_rate` — % of GUI tasks completed correctly |
| RAM | ~8 GB per VM |
| Storage | ~100 GB (VM images + Docker) |
| **Hard Requirement** | KVM / VT-x enabled in BIOS |

---

## CWF Setup

```bash
bash scripts/setup/setup_osworld.sh
```

What it does:
1. Verifies KVM support (`/proc/cpuinfo` vmx flags)
2. Checks nested virtualization status
3. Clones OSWorld, installs Python deps
4. Runs `quickstart.py` validation

### Verify KVM first
```bash
egrep -c '(vmx|svm)' /proc/cpuinfo   # must be > 0
# Enable nested virt if needed:
sudo modprobe -r kvm_intel
sudo modprobe kvm_intel nested=1
```

---

## Run

### 1. Start multimodal LLM server
OSWorld requires screenshot understanding — use a vision-capable model:
```bash
# Screenshot observation requires a multimodal model
# For accessibility_tree observation, standard LLM is sufficient
bash scripts/inference/start_vllm.sh --model 32b --cores 96
```

### 2. Quickstart validation (1 env, 1 task)
```bash
cd ~/cwf_agentic/osworld
conda activate agentic
python quickstart.py --provider_name docker
```

### 3. Production run (parallel VMs)
```bash
python scripts/python/run_multienv.py \
    --provider_name docker \
    --headless \
    --observation_type screenshot \
    --model local_llm \
    --sleep_after_execution 3 \
    --max_steps 15 \
    --num_envs 10 \
    --client_password password
```

### 4. Show results
```bash
python show_result.py --detailed
```

---

## CWF Scaling — `num_envs`

| num_envs | RAM needed | Env cores | Observation |
|---|---|---|---|
| 1 | 8 GB | 4–8 | Baseline |
| 4 | 32 GB | 16–32 | Good parallelism |
| 8 | 64 GB | 32–64 | Near BW limit with 32B model |
| 10 | 80 GB | 40–80 | Max recommended |

Pin VMs to env cores via KVM vCPU pinning:
```bash
# Each VM: 4 vCPUs → bind to physical cores 64–143
# Set vcpupin in libvirt domain XML or use Docker cpuset-cpus
```

---

## Config File

See [`configs/osworld.yaml`](../../configs/osworld.yaml).

---

## Domain-Level Results Schema

```
result.json:
{
  "libreoffice_calc": {"success": 12, "total": 45, "rate": 0.267},
  "chrome":          {"success": 8,  "total": 30, "rate": 0.267},
  ...
  "overall":         {"success": 64, "total": 369, "rate": 0.173}
}
```
