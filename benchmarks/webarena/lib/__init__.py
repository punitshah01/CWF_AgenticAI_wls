"""
benchmarks/webarena/lib/ — WebArena workload helper modules.

Mirrors pnpwls pattern where complex workloads (e.g. mysql_sysbench)
have a lib/ subpackage for lifecycle management, result parsing, etc.

For WebArena these are split as:
    result_parser.py  — Parse WebArena JSON output → success_rate, task counts
    env_manager.py    — Manage Docker service containers (shopping, reddit, etc.)
    core_scheduler.py — Topology-aware core assignment for LLM + Playwright
    ollama_metrics.py — HTTP proxy capturing per-request Ollama inference timing
"""
