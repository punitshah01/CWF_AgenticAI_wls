#!/usr/bin/env python3
"""
common/run_generic.py — Subprocess execution helpers for benchmark runners.

Provides ``run_cmd()`` (with retry + dry-run support) and ``stream_output()``
so benchmark runners do not need to embed subprocess boilerplate.
"""

import logging
import subprocess
import time
from typing import Iterator, List, Optional, Union

log = logging.getLogger(__name__)


def stream_output(proc: "subprocess.Popen[str]") -> Iterator[str]:
    """Yield stdout lines from a running subprocess, logging each at DEBUG.

    The caller is responsible for creating *proc* with ``stdout=PIPE`` and
    ``text=True``.

    Parameters
    ----------
    proc:
        A running ``subprocess.Popen`` instance.

    Yields
    ------
    str
        Each line (newline stripped) from ``proc.stdout``.
    """
    assert proc.stdout is not None, "Popen must be created with stdout=PIPE"
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip("\n")
        log.debug(line)
        yield line


def run_cmd(
    cmd: Union[str, List[str]],
    cwd: Optional[str] = None,
    timeout: Optional[int] = None,
    retries: int = 0,
    dry_run: bool = False,
) -> subprocess.CompletedProcess:
    """Run a shell command, log stdout/stderr, retry on non-zero exit.

    Parameters
    ----------
    cmd:
        Command string (shell=True) or list of tokens (shell=False).
    cwd:
        Working directory for the subprocess.
    timeout:
        Wall-clock timeout in seconds; raises ``subprocess.TimeoutExpired``
        if exceeded on the final attempt.
    retries:
        Number of *additional* attempts after the first failure.
        Total attempts = ``retries + 1``.  Uses exponential back-off.
    dry_run:
        If True, log the command string and return a synthetic success
        ``CompletedProcess`` without executing anything.

    Returns
    -------
    subprocess.CompletedProcess
        Result of the last (successful or final-failed) attempt.
        ``stdout`` and ``stderr`` are always strings.
    """
    shell = isinstance(cmd, str)
    display = cmd if shell else " ".join(cmd)
    log.info("$ %s", display)

    if dry_run:
        log.info("[dry-run] skipping execution")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    attempts = retries + 1
    last_result: Optional[subprocess.CompletedProcess] = None

    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            cmd,
            shell=shell,
            cwd=cwd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for line in result.stdout.splitlines():
            log.debug("[stdout] %s", line)
        for line in result.stderr.splitlines():
            (log.debug if result.returncode == 0 else log.warning)(
                "[stderr] %s", line
            )
        last_result = result
        if result.returncode == 0:
            return result
        log.warning(
            "Command failed (exit %d), attempt %d/%d: %s",
            result.returncode,
            attempt,
            attempts,
            display,
        )
        if attempt < attempts:
            time.sleep(2 ** attempt)  # exponential back-off before retry

    assert last_result is not None
    log.error("Command failed after %d attempt(s): %s", attempts, display)
    return last_result
