#!/usr/bin/env python3
"""
common/git_provenance.py — Result traceability via git metadata.

Embeds the current repo commit SHA, branch, and remote URL into every
result JSON file so results are always traceable back to source code.
"""

import logging
import subprocess
from typing import Dict, Optional

log = logging.getLogger(__name__)


def _git(args: list) -> Optional[str]:
    """Run a git subcommand and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_git_sha() -> Optional[str]:
    """Return the short HEAD commit SHA, or None if not a git repo."""
    return _git(["rev-parse", "--short", "HEAD"])


def get_repo_url() -> Optional[str]:
    """Return the remote origin URL, or None."""
    return _git(["remote", "get-url", "origin"])


def get_branch() -> Optional[str]:
    """Return the current branch name, or None."""
    return _git(["rev-parse", "--abbrev-ref", "HEAD"])


def get_provenance_dict() -> Dict[str, Optional[str]]:
    """Return a dict with ``sha``, ``repo_url``, and ``branch`` for the metadata block."""
    return {
        "sha": get_git_sha(),
        "repo_url": get_repo_url(),
        "branch": get_branch(),
    }
