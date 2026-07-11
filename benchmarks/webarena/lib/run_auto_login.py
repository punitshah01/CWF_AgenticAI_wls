#!/usr/bin/env python3
"""
benchmarks/webarena/lib/run_auto_login.py — Drop-in replacement invocation for
WebArena's browser_env/auto_login.py that surfaces real errors.

Upstream bug: auto_login.py's main() submits each site/pair login to a
ThreadPoolExecutor but NEVER calls .result() on those futures. Any exception
raised inside renew_comb() (Playwright timeout, changed login page markup,
network error, etc.) is silently discarded — the script exits 0 with ZERO
cookie files written, and callers have no way to know what actually failed.

This script imports the upstream module directly and re-runs the same login
logic sequentially (not threaded), printing the real exception for every
site/pair that fails, and exits non-zero only if EVERY login failed (partial
cookies are still useful — WebArena tasks are scoped per-site).

Usage (must run with cwd = the WebArena repo clone, same env vars as
browser_env/auto_login.py expects — SHOPPING, SHOPPING_ADMIN, REDDIT, GITLAB):
    python3 lib/run_auto_login.py
"""
import sys
import traceback
from itertools import combinations
from pathlib import Path

sys.path.insert(0, ".")

from browser_env.auto_login import SITES, renew_comb  # noqa: E402


def main() -> int:
    auth_folder = "./.auth"
    Path(auth_folder).mkdir(parents=True, exist_ok=True)

    pairs = list(combinations(SITES, 2))
    jobs = []
    for pair in pairs:
        # Matches upstream: auth doesn't work for these combos
        if "reddit" in pair and ("shopping" in pair or "shopping_admin" in pair):
            continue
        jobs.append(list(sorted(pair)))
    for site in SITES:
        jobs.append([site])

    n_ok, n_fail = 0, 0
    for comb in jobs:
        label = "+".join(comb)
        try:
            renew_comb(comb, auth_folder=auth_folder)
            print(f"[run_auto_login] OK   {label}")
            n_ok += 1
        except Exception as e:
            print(f"[run_auto_login] FAIL {label}: {type(e).__name__}: {e}")
            traceback.print_exc()
            n_fail += 1

    print(f"[run_auto_login] {n_ok} succeeded, {n_fail} failed out of {len(jobs)}")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
