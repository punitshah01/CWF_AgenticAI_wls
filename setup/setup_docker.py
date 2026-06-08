#!/usr/bin/env python3
"""
setup/setup_docker.py — Install Docker CE on Ubuntu or CentOS/RHEL.

Adds the official Docker CE repository and installs:
  docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin, docker-compose-plugin

Also:
  - Enables and starts the Docker daemon
  - Adds the current user to the 'docker' group
  - Validates the install with: docker run --rm hello-world

Usage:
  python3 setup/setup_docker.py
  python3 setup/setup_docker.py --dry-run
  python3 setup/setup_docker.py --skip-hello  # skip hello-world validation
"""

import argparse
import os
import shutil
import subprocess
import sys


def _run(cmd: str, dry_run: bool = False, check: bool = False) -> int:
    print(f"  $ {cmd}", flush=True)
    if dry_run:
        return 0
    r = subprocess.run(cmd, shell=True)
    if check and r.returncode != 0:
        print(f"[ERROR] Command failed: {cmd}", file=sys.stderr)
    return r.returncode


def detect_os_family() -> str:
    try:
        text = open("/etc/os-release").read()
        for line in text.splitlines():
            if line.startswith("ID="):
                distro_id = line.split("=", 1)[1].strip('"').lower()
                ubuntu_ids = {"ubuntu", "debian", "linuxmint", "pop"}
                centos_ids = {"centos", "rhel", "fedora", "rocky", "almalinux", "ol"}
                if distro_id in ubuntu_ids:
                    return "ubuntu"
                if distro_id in centos_ids:
                    return "centos"
    except OSError:
        pass
    if shutil.which("apt-get"):
        return "ubuntu"
    if shutil.which("dnf") or shutil.which("yum"):
        return "centos"
    return "unknown"


def install_ubuntu(dry_run: bool) -> None:
    print("\n[INFO] Installing Docker CE on Ubuntu/Debian ...", flush=True)
    script = (
        "sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true && "
        "sudo apt-get update -y && "
        "sudo apt-get install -y ca-certificates curl gnupg lsb-release && "
        "sudo install -m 0755 -d /etc/apt/keyrings && "
        "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | "
        "  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg && "
        "sudo chmod a+r /etc/apt/keyrings/docker.gpg && "
        "echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] "
        "  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable\" | "
        "  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null && "
        "sudo apt-get update -y && "
        "sudo apt-get install -y docker-ce docker-ce-cli containerd.io "
        "  docker-buildx-plugin docker-compose-plugin"
    )
    _run(script, dry_run)


def install_centos(dry_run: bool) -> None:
    print("\n[INFO] Installing Docker CE on CentOS/RHEL ...", flush=True)
    script = (
        "sudo dnf remove -y docker docker-client docker-client-latest docker-common "
        "  docker-latest docker-latest-logrotate docker-logrotate docker-engine 2>/dev/null || true && "
        "sudo dnf install -y yum-utils && "
        "sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo && "
        "sudo dnf install -y docker-ce docker-ce-cli containerd.io "
        "  docker-buildx-plugin docker-compose-plugin"
    )
    _run(script, dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Docker CE")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing")
    parser.add_argument("--skip-hello", action="store_true",
                        help="Skip hello-world validation after install")
    args = parser.parse_args()

    if shutil.which("docker") and not args.dry_run:
        print("[ OK ] Docker already installed:")
        subprocess.run(["docker", "--version"])
        sys.exit(0)

    family = detect_os_family()
    print(f"[INFO] OS family: {family}")

    if family == "ubuntu":
        install_ubuntu(args.dry_run)
    elif family == "centos":
        install_centos(args.dry_run)
    else:
        print(f"[ERROR] Unsupported OS family: {family}", file=sys.stderr)
        print("  Supported: Ubuntu/Debian, CentOS/RHEL/Rocky", file=sys.stderr)
        sys.exit(1)

    _run("sudo systemctl enable --now docker", args.dry_run)
    user = os.environ.get("USER", os.environ.get("LOGNAME", ""))
    if user:
        _run(f"sudo usermod -aG docker {user} || true", args.dry_run)

    if not args.skip_hello:
        print("\n[INFO] Validating Docker install ...")
        rc = _run("docker run --rm hello-world", args.dry_run)
        if rc != 0:
            print("[WARN] hello-world failed — you may need to re-login for group changes",
                  file=sys.stderr)
        else:
            print("[ OK ] Docker is working")

    print("\n[ OK ] Docker CE installed.")
    if user:
        print(f"[INFO] User '{user}' added to 'docker' group.")
        print("[INFO] Log out and back in (or run: newgrp docker) to use Docker without sudo.")


if __name__ == "__main__":
    main()
