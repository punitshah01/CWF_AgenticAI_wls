## What changed

- 
- 
- 

## How to test

```bash
# Dry-run smoke test
python scripts/setup.py --dry-run

# Syntax check all Python files
python -m py_compile $(find . -name "*.py" -not -path "./.venv/*" -not -path "./node_modules/*")

# Run the affected benchmark (replace with actual benchmark)
python benchmarks/appworld/run_appworld.py --dry-run --output-dir /tmp/test
```

## Benchmark results before/after

| Benchmark | Metric | Before | After |
|-----------|--------|--------|-------|
|           |        |        |       |

## Checklist

- [ ] `ruff check` passes (no new lint errors)
- [ ] `python -m py_compile` passes on all changed `.py` files
- [ ] `shellcheck` passes on all changed `.sh` files
- [ ] `python scripts/setup.py --dry-run` succeeds
- [ ] Benchmark dry-run smoke test passes
- [ ] README updated if CLI or config changed
