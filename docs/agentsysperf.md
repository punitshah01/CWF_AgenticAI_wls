# AgentSysPerf — Unified KPI, SLA, Phase Timing, and Capacity Sweep

## 1. Why

Raw task-success percentages and wall-clock runtime are not enough to make a CPU-tier /
SKU decision for agentic AI workloads. Two runs with the same success rate can have very
different **tail latency**, **cost per completed task**, and **agent density per vCPU**.
AgentSysPerf treats each agentic workload as a distributed control loop
(**Admit → Retrieve → Act → Decision → Commit**) and adds a normalized, workload-agnostic
KPI layer on top of the existing per-benchmark harness so that platform decisions can be
made on:

- Active agents per core/vCPU (density under SLO)
- p95 / p99 agent-loop latency
- Cost per completed task
- Capacity / saturation point under concurrency
- Tail-latency risk

## 2. Architecture

```
common/agentsysperf/
├── models.py               # TaskRecord, PhaseTiming, RunRecord, SLOConfig, CostModelConfig, ...
├── percentiles.py          # p50 / p95 / p99 / mean (linear-interpolation percentile)
├── sla.py                  # evaluate_slo() — pass/fail + explicit reasons
├── cost.py                 # compute_cost() — cost-per-completed-task model
├── queue_stats.py          # queue depth, token turnover, active_agents_per_vcpu
├── phases.py               # aggregate_phases() — measured / inferred / unavailable
├── summary.py              # build_run_summary() + write_run_artifacts() — single integration point
├── capacity.py             # detect_capacity() — saturation + recommended operating point
├── sweep.py                # run_concurrency_sweep() + write_sweep_artifacts()
├── merge.py                # cross-run merge into platform-level artifacts
└── runner_integration.py   # add_agentsysperf_args() / emit_agentsysperf_artifacts() glue used by each run.py
```

Every one of the 5 benchmark runners (`benchmarks/{workload}/run.py`) calls
`emit_agentsysperf_artifacts()` immediately after writing its existing `results.csv` /
`results.json` (unchanged). The call is wrapped so a bug in the analytics layer can never
break the primary result pipeline — on failure it prints a warning and the run still
completes normally.

## 3. KPI contract (per run)

| Field | Meaning |
|---|---|
| `active_agents` | Concurrent agent instances in the run |
| `vcpus` | Total logical CPUs available to the run (`CPUInfo.get_total_cores()`) |
| `active_agents_per_vcpu` | `active_agents / vcpus` — concurrency density |
| `loop_latency_p50_ms` / `p95_ms` / `p99_ms` | Agent-loop latency distribution (linear-interpolation percentile) |
| `loop_latency_approximation` | `null` when computed from true per-task timing, otherwise a label describing the best-effort approximation used |
| `cost_per_completed_task_usd` | See §5 |
| `queue_depth_mean` / `queue_depth_p95` | Only populated when a workload supplies queue-depth samples |
| `token_turnover_per_s` | `(tokens_in + tokens_out) / runtime_s` |
| `tasks_completed_per_hour` | `tasks_completed / (runtime_s / 3600)` |
| `slo_passed` / `slo_status` / `slo_failure_reason` | See §4 |

Per-phase metrics (`admit_ms`, `retrieve_ms`, `act_ms`, `decision_ms`, `commit_ms`) are
emitted with an explicit `source` tag:

- **measured** — true per-phase instrumentation exists for this workload/run.
- **inferred** — no per-phase telemetry; derived from the mean loop latency using a fixed
  phase-share heuristic (`admit 5% / retrieve 15% / act 45% / decision 25% / commit 10%`),
  clearly labeled so it is never mistaken for a measurement.
- **unavailable** — no data and no latency to infer from; field stays `null` with a
  `reason` string. The pipeline never crashes on missing data.

Any field that cannot be computed (e.g. `runtime_s == 0`) is `null`, never a fabricated
zero, so consumers can distinguish "no signal" from "measured zero."

## 4. SLA evaluation

Configured via `SLOConfig(p95_latency_ms_max, min_success_rate, max_cost_per_task_usd)`.
Any threshold left unset is not evaluated. `evaluate_slo()` returns `passed` plus a list of
machine-readable `failure_reasons` — including explicit `*_unavailable` reasons when a
threshold is configured but the corresponding metric could not be computed (missing data
is treated as "cannot verify," not as an automatic pass).

CLI flags on every runner (all optional, default = not enforced):

```
--sla-p95-ms 2000
--sla-min-success-rate 0.5
--sla-max-cost-per-task-usd 0.25
```

## 5. Cost model

```
compute_cost_component_usd = node_hourly_usd * (runtime_s / 3600)
energy_cost_component_usd  = ((avg_package_power_w + avg_dram_power_w) / 1000)
                              * (runtime_s / 3600) * energy_price_usd_per_kwh
total_cost_component_usd   = compute_cost_component_usd + energy_cost_component_usd
cost_per_completed_task_usd = total_cost_component_usd / tasks_completed
```

If `avg_package_power_w` or `energy_price_usd_per_kwh` is missing, the model falls back to
**compute-only mode** and sets an explicit `assumption` string naming which input was
missing — it never silently reports a partial number as a complete one.

CLI flags: `--node-hourly-usd` (default `5.0`), `--energy-price-usd-per-kwh` (default
unset ⇒ compute-only mode; RAPL-measured `pkg_power_w` / `dram_power_w` from
`TelemetryManager` are used automatically when available).

## 6. Phase mapping per workload

| Workload | Admit | Retrieve | Act | Decision | Commit |
|---|---|---|---|---|---|
| WebArena | task/config load | DOM/accessibility-tree read | Playwright action | LLM policy call | result write + eval |
| AppWorld | task instantiation | API/app state read | tool/API call | LLM function-call decision | evaluation write |
| OSWorld | VM/task setup | screenshot/a11y-tree capture | GUI action | LLM decision | step/result persistence |
| SWE-bench | instance checkout | repo/context retrieval | patch generation | agent loop decision | container evaluation |
| T-Bench | request admit | tool schema lookup | mock tool invocation | function-call selection | response commit |

Only **WebArena** currently has true per-task timing (`per_task_results[*].runtime_s`
captured by the existing per-task tracker), so it is the workload that reports **measured**
`loop_latency_p95_ms/p99_ms` today; the other four report a best-effort
`loop_latency_approximation` (typically `uniform_avg_from_total_runtime`, spreading the
run's total wall-clock time evenly across completed tasks) until per-task timing is added
to their harnesses — a documented follow-up (§13).

## 7. Concurrency sweep + capacity artifacts

```python
from common.agentsysperf.sweep import run_concurrency_sweep, write_sweep_artifacts

def run_fn(concurrency: int) -> dict:
    # Execute one measurement at this concurrency level using whatever
    # execution strategy the workload uses (e.g. --active-agents / --num-envs
    # / --max-workers), and return the aggregated result.
    ...
    return {
        "throughput_tasks_per_hour": ...,
        "loop_latencies_ms": [...],
        "slo_passed": ...,
    }

points = run_concurrency_sweep(run_fn, concurrency_points=[1, 2, 4, 8, 16], repetitions=2)
write_sweep_artifacts(output_dir, points)
```

Writes `sweep_results.csv` / `.json`, `saturation_summary.json`,
`recommended_operating_point.json`, and `capacity_summary.csv` / `.json`.

**Detection rules** (`common/agentsysperf/capacity.py`):
- **Saturation point** — first concurrency level where the SLA fails, or where the
  marginal throughput gain collapses below the `marginal_gain_floor` fraction (default
  `0.10` = 10%, configurable in `detect_capacity()`) of the best per-step gain seen so far.
- **Recommended operating point** — the highest SLA-passing concurrency below the
  saturation point whose p99/p95 tail-latency ratio stays under `1.5` ("stable tail").

## 8. Cross-run merge (platform/SKU comparison)

```bash
python3 -m common.agentsysperf.merge --runs-root results --out-dir results/agentsysperf
```

Scans `results/**/agentsysperf_summary.json` and writes:
- `workload_comparison_summary.csv` — one row per run, all workloads.
- `platform_capacity_summary.csv` — one row per workload: the best SLO-passing
  `active_agents_per_vcpu` operating point plus its p95/p99/cost.

## 9. End-to-end example

```bash
# 1. Run T-Bench with SLA enforcement and cost model enabled
python3 benchmarks/t-bench/run.py --model 8b \
  --sla-p95-ms 1500 --sla-min-success-rate 0.5 \
  --node-hourly-usd 4.20 --energy-price-usd-per-kwh 0.15

# 2. Inspect the normalized summary for that run
cat results/tbench/tbench_8b_64c_*/agentsysperf_summary.json

# 3. After running several workloads, build the platform-level comparison
python3 -m common.agentsysperf.merge --runs-root results --out-dir results/agentsysperf
cat results/agentsysperf/platform_capacity_summary.csv
```

### Sample `agentsysperf_summary.csv` (excerpt)

| workload | active_agents_per_vcpu | loop_latency_p95_ms | loop_latency_p99_ms | cost_per_completed_task_usd | slo_passed |
|---|---|---|---|---|---|
| tbench | 0.0625 | 1180.4 | 1305.9 | 0.0184 | True |
| webarena | 0.03125 | 42110.7 | 58732.1 | 0.512 | False |

## 10. Interpretation guide

- **Saturation point**: the concurrency level at which the platform stops delivering
  proportional throughput gains, or where SLA guarantees break down. Operating above this
  point trades tail latency (and SLA compliance) for marginal or no additional throughput.
- **Recommended operating point**: the concurrency to size a deployment at — it maximizes
  agents-per-vCPU while keeping SLA green and tail latency (p99/p95) bounded.
- **Tail-latency risk**: a high p99/p95 ratio (> 1.5) at a given concurrency indicates the
  loop latency distribution has a heavy tail — a subset of tasks/agents are being starved
  or blocked (queueing, retrieval contention, tool-call backpressure). Treat such points as
  unsafe for SLA-bound deployments even if the mean/median latency looks acceptable.

## 11. Troubleshooting: missing telemetry

- **`cost.assumption` mentions a missing input**: RAPL/EMON did not report package/DRAM
  power for the run (e.g. `--collect-rapl` was off, or telemetry failed to start). The
  cost model still runs in compute-only mode; pass `--collect-rapl` (default on for most
  runners) or check `telemetry/` logs in the run's output directory.
- **`loop_latency_p95_ms` is `null`**: no runtime/tasks-completed data was available (e.g.
  a `--dry-run`, or the underlying evaluation harness produced zero completed tasks).
  AgentSysPerf artifacts are skipped entirely during `--dry-run` (no change from legacy
  behavior).
- **All phases show `source: "unavailable"`**: neither true per-phase timing nor a mean
  loop latency was available to infer from. Verify the run actually completed tasks
  (`tasks_completed > 0`) and that `total_runtime_s` was recorded in `bench_results`.
- **`slo_status: "not_evaluated"`**: no `--sla-*` flags were passed for that run — this is
  the default, non-breaking state (SLA is opt-in).

## 12. Migration notes (legacy → AgentSysPerf)

- **Nothing is removed.** `results.csv`, `results.json`, and all existing per-workload
  files (e.g. WebArena's `per_task_results.csv`, `summary.csv`) are produced exactly as
  before.
- **New files are additive**, written into the same per-run output directory:
  `agentsysperf_summary.json`, `agentsysperf_summary.csv`, `phase_metrics.csv`,
  `slo_evaluation.json`.
- **New CLI flags default to inert/off** (`--sla-*` unset ⇒ SLA not enforced;
  `--energy-price-usd-per-kwh` unset ⇒ compute-only cost mode), so existing automation and
  scripts continue to work unmodified.
- To backfill AgentSysPerf artifacts for historical runs, re-derive them from the existing
  `results.json` fields using `common.agentsysperf.summary.build_run_summary()` directly —
  no re-run of the benchmark is required.

## 13. Known limitations and follow-up items

- Only WebArena currently emits *measured* per-task loop latency; AppWorld, OSWorld,
  SWE-bench, and T-Bench use the `uniform_avg_from_total_runtime` approximation until
  their harnesses are extended to record true per-task start/stop timestamps.
- Queue-depth and token-turnover metrics require the workload to supply sample data;
  none of the 5 runners currently instrument true queue depth, so `queue_depth_mean` /
  `queue_depth_p95` are `null` today for all workloads (explicitly, not silently).
- The concurrency-sweep saturation detector's marginal-gain-collapse rule is a
  single-pass heuristic and can be sensitive to measurement noise at a single
  concurrency point; use `repetitions > 1` in `run_concurrency_sweep()` to average out
  noise before it reaches the detector.
- The default phase-share heuristic (§6) is a fixed, documented approximation and not
  tuned per-model or per-hardware; replacing it with true per-phase instrumentation in
  each harness is the primary follow-up for improving phase-timing accuracy.
