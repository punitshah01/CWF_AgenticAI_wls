# Contributing to CWF Agentic AI Benchmarks

## How to Add a New Benchmark

### 1. Create the benchmark folder

```bash
BENCH=mybench   # use lowercase, no spaces
mkdir -p benchmarks/${BENCH}/{build,config}
```

### 2. Required files

| File | Purpose |
|------|---------|
| `benchmarks/${BENCH}/run.py` | Full benchmark implementation |
| `benchmarks/${BENCH}/run_${BENCH}.py` | Canonical runner using `common/cli_utils` |
| `benchmarks/${BENCH}/run_${BENCH}.sh` | Shell entry point (venv activate + tee log) |
| `benchmarks/${BENCH}/setup.py` | Self-contained dependency installer |
| `benchmarks/${BENCH}/build/build.sh` | `pip install -r requirements.txt` |
| `benchmarks/${BENCH}/build/requirements.txt` | Pip dependencies |
| `benchmarks/${BENCH}/config/default_config.yaml` | Must include standard fields (see below) |
| `benchmarks/${BENCH}/README.md` | What the benchmark measures, how to run it |

**Required fields in `default_config.yaml`:**
```yaml
model: "local-llm"
agent: "<agent_class>"
max_steps: 10
timeout_seconds: 300
output_dir: "results/<bench>"
log_level: "INFO"
```

### 3. `run_${BENCH}.py` template

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.cli_utils import get_base_parser, parse_config, setup_logging
from common.metadata import build_metadata

def build_parser():
    parser = get_base_parser(description="Run <bench> on CWF.")
    # add benchmark-specific args here
    return parser

def main():
    args = build_parser().parse_args()
    setup_logging(args.verbose)
    cfg = parse_config(args.config)
    # ... benchmark logic ...

if __name__ == "__main__":
    main()
```

### 4. `run_${BENCH}.sh` template

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
output_dir="results/<bench>"
# parse --output-dir from args ...
mkdir -p "${output_dir}"
[[ -f "${REPO_ROOT}/.venv/bin/activate" ]] && source "${REPO_ROOT}/.venv/bin/activate"
python "${SCRIPT_DIR}/run_<bench>.py" "$@" 2>&1 | tee -a "${output_dir}/run.log"
```

### 5. Add a stub to `configs/`

```yaml
# configs/<bench>.yaml
_canonical_config: benchmarks/<bench>/config/default_config.yaml
```

### 6. Add CI smoke test

In `.github/workflows/ci.yml`, add a step to the `dry-run-smoke` job:

```yaml
- name: Smoke — <bench> dry-run
  run: python benchmarks/<bench>/run_<bench>.py --dry-run --output-dir /tmp/test_<bench>
```

---

## Coding Conventions

### Python

- Follow **PEP 8**; maximum line length is 100 characters (ruff enforces this)
- All runner files must have a `if __name__ == "__main__": main()` guard
- Use `logging` (never bare `print()`) in runner and utility code
- No hardcoded paths — all paths via config or CLI args
- Idempotent installs: use `pip install` (skips already-satisfied constraints)
- Python 3.9+ compatible: no `str | None` union syntax (use `Optional[str]`)

### Shell scripts

- Always start with `#!/bin/bash` and `set -euo pipefail`
- Quote all variable expansions: `"${VAR}"` not `$VAR`
- Use `shellcheck` to validate before committing

### Result JSON schema

```json
{
  "metadata": {
    "benchmark":  "<name>",
    "timestamp":  "<ISO8601Z>",
    "provenance": { "sha": "...", "branch": "...", "repo_url": "..." },
    "system":     { ... },
    "config":     { ... }
  },
  "results": {
    "<kpi_name>": <value>
  }
}
```

---

## Running CI Locally

```bash
# Lint
pip install ruff
ruff check common/ benchmarks/ scripts/ setup/ misc/ --ignore E501,E402

# Syntax check (Python 3.9)
find . -name "*.py" -not -path "./.venv/*" | xargs python -m py_compile

# Shellcheck
find . -name "*.sh" | xargs shellcheck --severity=warning

# Dry-run smoke test
python scripts/setup.py --dry-run --skip-system --skip-docker --skip-conda --skip-pip
python benchmarks/appworld/run_appworld.py --dry-run --output-dir /tmp/test
```
