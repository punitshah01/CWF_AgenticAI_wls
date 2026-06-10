#!/usr/bin/env python3
"""
common/docker_utils.py — Docker helpers for running benchmarks in containers.

Provides thin, logged wrappers around the ``docker`` CLI so benchmark
runners do not need to embed subprocess boilerplate.
"""

import logging
import subprocess
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


def pull_image(image_name: str) -> None:
    """Pull a Docker image, streaming progress lines to the logger.

    Parameters
    ----------
    image_name:
        Full image reference, e.g. ``ubuntu:22.04`` or
        ``ghcr.io/princeton-nlp/swe-bench:latest``.

    Raises
    ------
    RuntimeError
        If ``docker pull`` exits with a non-zero return code.
    """
    log.info("Pulling Docker image: %s", image_name)
    result = subprocess.run(
        ["docker", "pull", image_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in result.stdout.splitlines():
        log.debug("[docker pull] %s", line)
    if result.returncode != 0:
        raise RuntimeError(
            f"docker pull {image_name!r} failed (exit {result.returncode})"
        )
    log.info("Image ready: %s", image_name)


def run_container(
    image: str,
    cmd: List[str],
    volumes: Optional[Dict[str, str]] = None,
    env_vars: Optional[Dict[str, str]] = None,
    name: Optional[str] = None,
    remove: bool = True,
) -> subprocess.CompletedProcess:
    """Run a Docker container and return the CompletedProcess (stdout/stderr captured).

    Parameters
    ----------
    image:
        Docker image name.
    cmd:
        Command + arguments to pass after the image name.
    volumes:
        ``{host_path: container_path}`` bind-mount mapping.
    env_vars:
        ``{KEY: VALUE}`` environment variables to set inside the container.
    name:
        Optional ``--name`` for the container (useful for later lookups).
    remove:
        If True (default), pass ``--rm`` so the container is deleted on exit.

    Returns
    -------
    subprocess.CompletedProcess
        Completed process with ``.stdout`` and ``.stderr`` as strings.
    """
    docker_cmd: List[str] = ["docker", "run"]
    if remove:
        docker_cmd.append("--rm")
    if name:
        docker_cmd += ["--name", name]
    for host_path, container_path in (volumes or {}).items():
        docker_cmd += ["-v", f"{host_path}:{container_path}"]
    for k, v in (env_vars or {}).items():
        docker_cmd += ["-e", f"{k}={v}"]
    docker_cmd.append(image)
    docker_cmd.extend(cmd)

    log.debug("Running: %s", " ".join(docker_cmd))
    return subprocess.run(
        docker_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def container_exists(name: str) -> bool:
    """Return True if a container with *name* is currently running.

    Parameters
    ----------
    name:
        Container name (not image name) to check.
    """
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return name in result.stdout.splitlines()
