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
logic, but with .result() actually checked so real errors surface. Each
renew_comb() call gets its OWN thread (matching upstream's design) rather
than running sequentially in-process — renew_comb() has no try/finally
around its sync_playwright() context manager, so if one call raises before
reaching context_manager.__exit__(), it leaves that THREAD's Playwright
driver/event-loop in a broken state ("Sync API inside the asyncio loop") —
running strictly sequentially in a single thread lets one failure poison
every subsequent attempt. A fresh thread per call avoids that.

Usage (must run with cwd = the WebArena repo clone, same env vars as
browser_env/auto_login.py expects — SHOPPING, SHOPPING_ADMIN, REDDIT, GITLAB):
    python3 lib/run_auto_login.py
"""
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

sys.path.insert(0, ".")

from browser_env.auto_login import SITES, renew_comb  # noqa: E402


def _run_one(comb):
    """Run renew_comb in a dedicated thread and return (comb, exc_or_None)."""
    try:
        renew_comb(comb, auth_folder="./.auth")
        return comb, None
    except Exception as e:  # noqa: BLE001 — must catch everything to report it
        return comb, e


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
    # One thread per job (not a shared pool reused across calls) so a
    # poisoned Playwright event-loop state from a failed attempt can never
    # leak into the next job's thread.
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [executor.submit(_run_one, comb) for comb in jobs]
        for future in futures:
            comb, exc = future.result()
            label = "+".join(comb)
            if exc is None:
                print(f"[run_auto_login] OK   {label}")
                n_ok += 1
            else:
                print(f"[run_auto_login] FAIL {label}: {type(exc).__name__}: {exc}")
                traceback.print_exception(type(exc), exc, exc.__traceback__)
                n_fail += 1

    print(f"[run_auto_login] {n_ok} succeeded, {n_fail} failed out of {len(jobs)}")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
