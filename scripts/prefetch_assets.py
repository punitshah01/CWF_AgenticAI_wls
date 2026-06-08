#!/usr/bin/env python3
"""
prefetch_assets.py — CWF Agentic AI: One-time Asset Downloader & Registry Mirror
==================================================================================
Downloads all Docker images and large static files ONCE, then mirrors them to a
local registry (or Intel Artifactory) so that every subsequent run is fully offline.

Actions
-------
  pull             Pull all Docker images from upstream + download large files
  push             Re-tag pulled images and push to local/artifactory registry
  start-registry   Spin up a local registry:2 container at localhost:5000
  stop-registry    Stop and remove the local registry container
  status           Show which assets are cached / missing
  export-tar       Save all Docker images to .tar.gz files (for sneakernet transfer)
  import-tar       Load .tar.gz image archives into Docker

Quick start (first machine, internet access)
--------------------------------------------
  # 1. Start local registry on the lab server
  python3 scripts/prefetch_assets.py start-registry

  # 2. Pull everything from internet and push to local registry
  python3 scripts/prefetch_assets.py pull
  python3 scripts/prefetch_assets.py push

  # 3. On SUT (offline), point setup at local registry
  python3 scripts/setup.py --registry localhost:5000

  # Or export to tarball for air-gapped transfer
  python3 scripts/prefetch_assets.py export-tar --out /data/cwf_images.tar.gz

Registry override (choose one)
-------------------------------
  --registry localhost:5000              # local registry (default)
  --registry myhost.lab:5000             # remote registry on lab server
  --registry ubit-artifactory-or.intel.com/docker-local  # Intel Artifactory
  REGISTRY_URL=...  (env var)            # same effect

Usage
-----
  python3 scripts/prefetch_assets.py pull [--benchmarks swebench webarena] [--include-optional]
  python3 scripts/prefetch_assets.py pull-models [--models 8b 32b]  # download GGUF files
  python3 scripts/prefetch_assets.py push [--registry <url>]
  python3 scripts/prefetch_assets.py status
  python3 scripts/prefetch_assets.py start-registry [--port 5000]
  python3 scripts/prefetch_assets.py stop-registry
  python3 scripts/prefetch_assets.py export-tar --out /path/to/archive.tar.gz
  python3 scripts/prefetch_assets.py import-tar --in /path/to/archive.tar.gz
  python3 scripts/prefetch_assets.py --dry-run pull

Internet-access requirements by benchmark
------------------------------------------
  SWE-bench  : Docker images (DockerHub) + git clone SWE-bench/SWE-bench + dataset (HuggingFace)
  WebArena   : 6 Docker images (DockerHub)
  OSWorld    : Docker image + 2 QEMU VM images (HuggingFace, ~19 GB total)
  AppWorld   : `appworld install` + `appworld download data` (~10 GB, no wget URL)
  T-Bench    : pip packages only — no large downloads
  Inference  : GGUF model files (HuggingFace, bartowski repos) OR vLLM auto-download
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_YAML = REPO_ROOT / "configs" / "assets.yaml"
ASSETS_DIR = REPO_ROOT / "assets"
MANIFEST_FILE = ASSETS_DIR / "manifest.json"
REGISTRY_DATA_DIR = ASSETS_DIR / "registry-data"
REGISTRY_CONTAINER = "cwf-local-registry"
DEFAULT_REGISTRY = os.environ.get("REGISTRY_URL", "localhost:5000")
DEFAULT_NAMESPACE = "cwf-agentic"

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

class Color:
    BLUE   = "\033[94m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def log(msg: str, level: str = "info") -> None:
    colors = {"info": Color.BLUE, "ok": Color.GREEN, "warn": Color.YELLOW, "error": Color.RED}
    prefix = {"info": "[INFO]", "ok": "[ OK ]", "warn": "[WARN]", "error": "[ERR ]"}
    c = colors.get(level, "")
    p = prefix.get(level, "[    ]")
    print(f"{c}{Color.BOLD}{p}{Color.RESET}{c} {msg}{Color.RESET}", flush=True)

def banner(title: str) -> None:
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*70}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}  {title}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}{'='*70}{Color.RESET}\n")

def run(cmd: str, dry_run: bool = False, check: bool = True,
        capture: bool = False) -> Optional[subprocess.CompletedProcess]:
    print(f"  $ {cmd}", flush=True)
    if dry_run:
        return None
    result = subprocess.run(
        cmd, shell=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )
    if check and result.returncode != 0:
        log(f"Command failed (exit {result.returncode}): {cmd}", "error")
    return result

def load_yaml() -> Dict:
    """Load configs/assets.yaml. Returns dict."""
    try:
        import yaml
        with open(ASSETS_YAML) as f:
            return yaml.safe_load(f)
    except ImportError:
        log("pyyaml not found. Installing...", "warn")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyyaml"],
                       check=True)
        import yaml
        with open(ASSETS_YAML) as f:
            return yaml.safe_load(f)

def load_manifest() -> Dict:
    """Load assets/manifest.json. Returns empty dict if not found."""
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    return {"images": {}, "files": {}, "last_updated": None}

def save_manifest(manifest: Dict) -> None:
    """Write assets/manifest.json atomically."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = datetime.utcnow().isoformat() + "Z"
    tmp = MANIFEST_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=2)
    tmp.replace(MANIFEST_FILE)

def image_exists_locally(image: str) -> bool:
    """Return True if Docker image is present on this host."""
    r = subprocess.run(
        f"docker image inspect {image} --format '{{{{.Id}}}}'",
        shell=True, capture_output=True, text=True
    )
    return r.returncode == 0 and bool(r.stdout.strip())

def sha256_file(path: Path, block_size: int = 1 << 20) -> str:
    """Compute SHA-256 of a file efficiently."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def collect_images(config: Dict, benchmarks: List[str],
                   include_optional: bool) -> List[Dict]:
    """Return flat list of image dicts that match benchmark + required filters."""
    images = []
    for group, img_list in config.get("docker_images", {}).items():
        if group == "utility":
            images.extend(img_list)
            continue
        if benchmarks and group not in benchmarks:
            continue
        for img in img_list:
            if img.get("required", True) or include_optional:
                images.append({**img, "group": group})
    return images

def collect_files(config: Dict, benchmarks: List[str],
                  include_optional: bool) -> List[Dict]:
    """Return flat list of file dicts that match benchmark + required filters."""
    files = []
    for key, fdef in config.get("large_files", {}).items():
        bench = fdef.get("benchmark", "all")
        if bench != "all" and benchmarks and bench not in benchmarks:
            continue
        if fdef.get("required", True) or include_optional:
            files.append({**fdef, "key": key})
    return files

# ─────────────────────────────────────────────────────────────────────────────
# Registry management
# ─────────────────────────────────────────────────────────────────────────────

def start_registry(port: int, dry_run: bool) -> None:
    banner(f"Starting local Docker registry on port {port}")

    # Check if already running
    r = subprocess.run(
        f"docker inspect {REGISTRY_CONTAINER} --format '{{{{.State.Status}}}}'",
        shell=True, capture_output=True, text=True
    )
    if r.returncode == 0 and "running" in r.stdout:
        log(f"Registry container '{REGISTRY_CONTAINER}' already running.", "ok")
        return

    REGISTRY_DATA_DIR.mkdir(parents=True, exist_ok=True)

    run(
        f"docker run -d --restart=always --name {REGISTRY_CONTAINER} "
        f"-p {port}:{port} "
        f"-v {REGISTRY_DATA_DIR}:/var/lib/registry "
        f"registry:2",
        dry_run=dry_run,
    )

    if not dry_run:
        log("Waiting for registry to be ready...", "info")
        for _ in range(10):
            r = subprocess.run(
                f"curl -sf http://localhost:{port}/v2/",
                shell=True, capture_output=True
            )
            if r.returncode == 0:
                break
            time.sleep(1)

    log(f"Local registry running at localhost:{port}", "ok")
    log("Add to /etc/docker/daemon.json if HTTP (no TLS):", "info")
    print(f'      {{"insecure-registries": ["localhost:{port}"]}}')
    print()

def stop_registry(dry_run: bool) -> None:
    banner("Stopping local registry")
    run(f"docker stop {REGISTRY_CONTAINER} && docker rm {REGISTRY_CONTAINER}",
        dry_run=dry_run, check=False)
    log("Registry stopped.", "ok")

# ─────────────────────────────────────────────────────────────────────────────
# Pull: Docker images
# ─────────────────────────────────────────────────────────────────────────────

def pull_images(images: List[Dict], dry_run: bool) -> Dict:
    """Pull each image from upstream. Returns updated manifest entries."""
    banner(f"Pulling {len(images)} Docker images")
    manifest_images = {}

    for img in images:
        source = img["source"]
        tag = img.get("tag", "latest")
        full = f"{source}:{tag}"
        size_gb = img.get("size_gb", 0)

        log(f"Pulling {full}  (~{size_gb:.1f} GB)", "info")
        result = run(f"docker pull {full}", dry_run=dry_run, check=False)

        success = dry_run or (result and result.returncode == 0)
        if success:
            # Get image ID
            id_result = subprocess.run(
                f"docker image inspect {full} --format '{{{{.Id}}}}'",
                shell=True, capture_output=True, text=True
            ) if not dry_run else None
            image_id = (id_result.stdout.strip() if id_result else "dry-run")
            manifest_images[full] = {
                "source": full,
                "pulled_at": datetime.utcnow().isoformat() + "Z",
                "image_id": image_id,
                "group": img.get("group", ""),
                "size_gb": size_gb,
                "status": "pulled",
            }
            log(f"  {full} → OK", "ok")
        else:
            log(f"  {full} → FAILED (will retry later)", "error")
            manifest_images[full] = {
                "source": full,
                "status": "pull_failed",
                "pulled_at": datetime.utcnow().isoformat() + "Z",
            }

    return manifest_images

# ─────────────────────────────────────────────────────────────────────────────
# Push: tag and push to registry
# ─────────────────────────────────────────────────────────────────────────────

def push_images(images: List[Dict], registry: str, namespace: str,
                dry_run: bool) -> None:
    banner(f"Pushing images to registry: {registry}/{namespace}")

    for img in images:
        source = img["source"]
        tag = img.get("tag", "latest")
        full = f"{source}:{tag}"

        # Build target name: strip any existing registry prefix, then add ours
        basename = source.split("/")[-1]
        target = f"{registry}/{namespace}/{basename}:{tag}"

        if not dry_run and not image_exists_locally(full):
            log(f"  {full} not found locally — skipping push (run 'pull' first)", "warn")
            continue

        log(f"  {full} → {target}", "info")
        run(f"docker tag {full} {target}", dry_run=dry_run, check=False)
        result = run(f"docker push {target}", dry_run=dry_run, check=False)

        if result and result.returncode != 0:
            log(f"  Push failed for {target}. Check registry access.", "error")
        elif not dry_run:
            log(f"  Pushed {target}", "ok")

# ─────────────────────────────────────────────────────────────────────────────
# Pull: large files
# ─────────────────────────────────────────────────────────────────────────────

def download_file(url: str, dest: Path, expected_sha256: str,
                  dry_run: bool) -> bool:
    """Download a file with resume support. Verifies SHA-256 if provided."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and expected_sha256:
        log(f"  Verifying existing {dest.name} ...", "info")
        actual = sha256_file(dest)
        if actual == expected_sha256:
            log(f"  {dest.name} already cached and verified. Skipping.", "ok")
            return True
        log(f"  SHA-256 mismatch for {dest.name} — re-downloading.", "warn")

    elif dest.exists():
        log(f"  {dest.name} already cached (no sha256 to verify). Skipping.", "ok")
        return True

    size_info = ""
    log(f"  Downloading {dest.name}{size_info} ...", "info")
    log(f"    URL: {url}", "info")

    # Use wget -c (resume) if available, else curl --continue-at
    if shutil.which("wget"):
        cmd = f"wget -c --progress=bar:force -O {dest} '{url}'"
    elif shutil.which("curl"):
        cmd = f"curl -L --continue-at - -o {dest} '{url}'"
    else:
        log("Neither wget nor curl found. Cannot download large files.", "error")
        return False

    result = run(cmd, dry_run=dry_run, check=False)

    if dry_run:
        return True

    if not result or result.returncode != 0:
        log(f"  Download failed for {dest.name}", "error")
        return False

    if expected_sha256:
        actual = sha256_file(dest)
        if actual != expected_sha256:
            log(f"  SHA-256 mismatch after download! Expected {expected_sha256[:16]}..., "
                f"got {actual[:16]}...", "error")
            return False
        log(f"  SHA-256 verified: {actual[:16]}...", "ok")

    log(f"  {dest.name} downloaded OK ({dest.stat().st_size / 1e9:.2f} GB)", "ok")
    return True

def pull_files(files: List[Dict], dry_run: bool) -> Dict:
    """Download all large static files. Returns updated manifest entries."""
    banner(f"Downloading {len(files)} large files")
    manifest_files = {}

    for fdef in files:
        key = fdef["key"]
        url = fdef["url"]
        dest = REPO_ROOT / fdef["dest"]
        sha256 = fdef.get("sha256", "")
        size_gb = fdef.get("size_gb", 0)

        log(f"[{key}]  {fdef.get('description', '')}  (~{size_gb:.1f} GB)", "info")
        ok = download_file(url, dest, sha256, dry_run)

        manifest_files[key] = {
            "key": key,
            "url": url,
            "dest": str(dest),
            "status": "downloaded" if ok else "failed",
            "downloaded_at": datetime.utcnow().isoformat() + "Z",
            "size_bytes": dest.stat().st_size if (dest.exists() and not dry_run) else 0,
        }

        # Record sha256 if not set yet (first download)
        if ok and not sha256 and dest.exists() and not dry_run:
            computed = sha256_file(dest)
            manifest_files[key]["sha256"] = computed
            log(f"  SHA-256: {computed} (update assets.yaml to persist)", "info")

    return manifest_files

# ─────────────────────────────────────────────────────────────────────────────
# Export / Import (tar)
# ─────────────────────────────────────────────────────────────────────────────

def export_images_tar(images: List[Dict], output: Path, dry_run: bool) -> None:
    """Save all Docker images to a single .tar.gz archive."""
    banner(f"Exporting Docker images to {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    full_names = [f"{img['source']}:{img.get('tag', 'latest')}" for img in images]
    image_list = " ".join(full_names)

    # docker save produces a tar with all images
    run(f"docker save {image_list} | gzip > {output}", dry_run=dry_run, check=False)

    if not dry_run and output.exists():
        size = output.stat().st_size / 1e9
        log(f"Exported {len(full_names)} images → {output}  ({size:.1f} GB)", "ok")

def import_images_tar(archive: Path, dry_run: bool) -> None:
    """Load images from a .tar.gz archive into Docker."""
    banner(f"Importing Docker images from {archive}")

    if not archive.exists():
        log(f"Archive not found: {archive}", "error")
        return

    run(f"docker load < {archive}", dry_run=dry_run, check=False)
    log("Import complete.", "ok")

# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

def print_status(config: Dict, benchmarks: List[str]) -> None:
    banner("Asset Cache Status")
    manifest = load_manifest()

    # Docker images
    print(f"  {'IMAGE':<55} {'STATUS':<12} {'SIZE GB':>8}")
    print(f"  {'-'*55} {'-'*12} {'-'*8}")

    for group, img_list in config.get("docker_images", {}).items():
        if benchmarks and group not in benchmarks and group != "utility":
            continue
        for img in img_list:
            source = img["source"]
            tag = img.get("tag", "latest")
            full = f"{source}:{tag}"
            present = image_exists_locally(full)
            status = f"{Color.GREEN}cached{Color.RESET}" if present else f"{Color.YELLOW}missing{Color.RESET}"
            size_gb = img.get("size_gb", 0)
            req = "" if img.get("required", True) else " [opt]"
            print(f"  {full[:55]:<55} {status:<20} {size_gb:>6.1f}{req}")

    # Large files
    print()
    print(f"  {'FILE':<45} {'STATUS':<12} {'SIZE GB':>8}")
    print(f"  {'-'*45} {'-'*12} {'-'*8}")

    for key, fdef in config.get("large_files", {}).items():
        bench = fdef.get("benchmark", "all")
        if bench != "all" and benchmarks and bench not in benchmarks:
            continue
        dest = REPO_ROOT / fdef["dest"]
        present = dest.exists()
        status = f"{Color.GREEN}cached{Color.RESET}" if present else f"{Color.YELLOW}missing{Color.RESET}"
        size_gb = fdef.get("size_gb", 0)
        req = "" if fdef.get("required", True) else " [opt]"
        print(f"  {key:<45} {status:<20} {size_gb:>6.1f}{req}")

    print()
    if manifest.get("last_updated"):
        print(f"  Manifest last updated: {manifest['last_updated']}")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# generate_registry_compose: create docker-compose for local registry
# ─────────────────────────────────────────────────────────────────────────────

def generate_registry_compose(port: int) -> None:
    """Write docker-compose.local-registry.yml for local registry."""
    content = f"""# docker-compose.local-registry.yml
# ─────────────────────────────────────────────────────────────────────────────
# Local Docker registry mirror for CWF Agentic AI workloads.
# Run once on a machine with internet access to cache all images.
#
# Usage:
#   docker compose -f docker-compose.local-registry.yml up -d
#   python3 scripts/prefetch_assets.py pull
#   python3 scripts/prefetch_assets.py push --registry localhost:{port}
# ─────────────────────────────────────────────────────────────────────────────
version: "3.9"

services:
  registry:
    image: registry:2
    container_name: {REGISTRY_CONTAINER}
    restart: always
    ports:
      - "{port}:{port}"
    environment:
      REGISTRY_HTTP_ADDR: "0.0.0.0:{port}"
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
      REGISTRY_LOG_LEVEL: "warn"
    volumes:
      - {REGISTRY_DATA_DIR}:/var/lib/registry
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:{port}/v2/"]
      interval: 10s
      timeout: 5s
      retries: 3
"""
    out = REPO_ROOT / "docker-compose.local-registry.yml"
    with open(out, "w") as f:
        f.write(content)
    log(f"Generated {out}", "ok")

# ─────────────────────────────────────────────────────────────────────────────
# generate_daemon_json: helper to configure insecure registry
# ─────────────────────────────────────────────────────────────────────────────

def print_daemon_json_hint(registry: str) -> None:
    """Print instructions to add insecure registry to Docker daemon."""
    # Only needed if registry has no TLS
    if registry.startswith("localhost") or registry.startswith("127."):
        print()
        print(f"  {Color.YELLOW}NOTE:{Color.RESET} If Docker rejects pushes/pulls from {registry}:")
        print("  Add to /etc/docker/daemon.json and restart Docker:")
        print(f'    {{"insecure-registries": ["{registry}"]}}')
        print("    sudo systemctl restart docker")
        print()

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CWF Agentic AI — Asset Prefetcher & Registry Mirror",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "action",
        choices=["pull", "pull-models", "push", "start-registry", "stop-registry",
                 "status", "export-tar", "import-tar"],
        help="Action to perform",
    )
    parser.add_argument(
        "--benchmarks", nargs="+",
        choices=["swebench", "webarena", "osworld", "appworld", "tbench"],
        default=None,
        help="Limit to specific benchmarks (default: all)",
    )
    parser.add_argument(
        "--include-optional", action="store_true",
        help="Also pull/download optional (non-required) assets",
    )
    parser.add_argument(
        "--skip-images", action="store_true",
        help="Skip Docker image operations (pull/push only large files)",
    )
    parser.add_argument(
        "--skip-files", action="store_true",
        help="Skip large file downloads (pull/push only Docker images)",
    )
    parser.add_argument(
        "--registry", default=DEFAULT_REGISTRY,
        help=f"Registry URL for push action. Default: {DEFAULT_REGISTRY}. "
             "Override with REGISTRY_URL env var.",
    )
    parser.add_argument(
        "--namespace", default=DEFAULT_NAMESPACE,
        help=f"Registry namespace/path prefix. Default: {DEFAULT_NAMESPACE}",
    )
    parser.add_argument(
        "--port", type=int, default=5000,
        help="Port for local registry container (start-registry). Default: 5000",
    )
    parser.add_argument(
        "--out", type=Path,
        help="Output path for export-tar (e.g. /data/cwf_images.tar.gz)",
    )
    parser.add_argument(
        "--in", dest="archive_in", type=Path,
        help="Input archive path for import-tar",
    )
    parser.add_argument(
        "--models", nargs="+", default=["8b", "32b"],
        choices=["8b", "32b", "32b-qwen", "70b"],
        help="GGUF model sizes to download for pull-models action. Default: 8b 32b",
    )
    parser.add_argument(
        "--quant", default="Q4_K_M",
        help="GGUF quantization format. Default: Q4_K_M",
    )
    parser.add_argument(
        "--models-dir", default="assets/models",
        help="Directory to store downloaded GGUF files. Default: assets/models",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print commands without executing them",
    )
    return parser.parse_args()


# ── GGUF model download ────────────────────────────────────────────────────────

# Maps model size shortcut → (HF repo, filename template)
_GGUF_MODELS = {
    "8b":      ("bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
                "Meta-Llama-3.1-8B-Instruct-{quant}.gguf"),
    "32b":     ("bartowski/Qwen2.5-Coder-32B-Instruct-GGUF",
                "Qwen2.5-Coder-32B-Instruct-{quant}.gguf"),
    "32b-qwen":("bartowski/Qwen2.5-32B-Instruct-GGUF",
                "Qwen2.5-32B-Instruct-{quant}.gguf"),
    "70b":     ("bartowski/Meta-Llama-3.1-70B-Instruct-GGUF",
                "Meta-Llama-3.1-70B-Instruct-{quant}.gguf"),
}

_GGUF_SIZES_GB = {"8b": 4.9, "32b": 19.5, "32b-qwen": 19.5, "70b": 40.0}


def pull_models(model_sizes: List[str], quant: str, models_dir: Path,
                dry_run: bool) -> None:
    """Download GGUF model files via huggingface-cli."""
    banner(f"Downloading GGUF models ({', '.join(model_sizes)}, quant={quant})")
    models_dir.mkdir(parents=True, exist_ok=True)

    if not shutil.which("huggingface-cli"):
        log("huggingface-cli not found. Install with: pip install huggingface_hub[cli]", "error")
        if not dry_run:
            return

    for size in model_sizes:
        entry = _GGUF_MODELS.get(size)
        if not entry:
            log(f"Unknown model size: {size}", "warn")
            continue
        hf_repo, filename_tmpl = entry
        filename = filename_tmpl.format(quant=quant)
        dest = models_dir / filename.lower()
        size_gb = _GGUF_SIZES_GB.get(size, 0)

        if dest.exists() and not dry_run:
            log(f"  {filename} already cached at {dest}", "ok")
            continue

        log(f"  Downloading {size} ({size_gb:.1f} GB): {hf_repo} / {filename}", "info")
        cmd = (
            f"huggingface-cli download {hf_repo} "
            f"--include '*{quant}*' "
            f"--local-dir {models_dir}"
        )
        run(cmd, dry_run=dry_run, check=False)

    log("Model download complete. Pass --models-dir to start_llamacpp.py:", "ok")
    print(f"    python3 scripts/inference/start_llamacpp.py --models-dir {models_dir} --model 8b")


def main() -> None:
    args = parse_args()
    config = load_yaml()
    manifest = load_manifest()

    benchmarks = args.benchmarks or []
    images = collect_images(config, benchmarks, args.include_optional)
    files = collect_files(config, benchmarks, args.include_optional)

    # ── status ────────────────────────────────────────────────────────────
    if args.action == "status":
        print_status(config, benchmarks)
        return

    # ── start-registry ────────────────────────────────────────────────────
    if args.action == "start-registry":
        generate_registry_compose(args.port)
        start_registry(args.port, args.dry_run)
        print_daemon_json_hint(f"localhost:{args.port}")
        return

    # ── stop-registry ─────────────────────────────────────────────────────
    if args.action == "stop-registry":
        stop_registry(args.dry_run)
        return

    # ── pull-models ───────────────────────────────────────────────────────
    if args.action == "pull-models":
        pull_models(args.models, args.quant, Path(args.models_dir), args.dry_run)
        return

    # ── pull ──────────────────────────────────────────────────────────────
    if args.action == "pull":
        banner("CWF Agentic AI — Asset Prefetch")
        print(f"  Benchmarks : {', '.join(benchmarks) if benchmarks else 'all'}")
        print(f"  Images     : {len(images)}")
        print(f"  Files      : {len(files)}")
        print()

        if not args.skip_images:
            new_img_entries = pull_images(images, args.dry_run)
            manifest["images"].update(new_img_entries)
            save_manifest(manifest)

        if not args.skip_files:
            new_file_entries = pull_files(files, args.dry_run)
            manifest["files"].update(new_file_entries)
            save_manifest(manifest)

        banner("Pull Complete")
        ok_imgs = sum(1 for v in manifest["images"].values() if v.get("status") == "pulled")
        ok_files = sum(1 for v in manifest["files"].values() if v.get("status") == "downloaded")
        print(f"  Docker images cached : {ok_imgs}")
        print(f"  Large files cached   : {ok_files}")
        print()
        log("Run 'push' to mirror all assets to your registry:", "info")
        print(f"    python3 scripts/prefetch_assets.py push --registry {args.registry}")
        print()
        return

    # ── push ──────────────────────────────────────────────────────────────
    if args.action == "push":
        if not args.skip_images:
            push_images(images, args.registry, args.namespace, args.dry_run)
        print_daemon_json_hint(args.registry)

        # Update manifest with push registry
        manifest["pushed_to"] = args.registry
        manifest["pushed_at"] = datetime.utcnow().isoformat() + "Z"
        save_manifest(manifest)

        banner("Push Complete")
        log(f"Images available at {args.registry}/{args.namespace}/<name>:<tag>", "ok")
        log("To use in setup.py:", "info")
        print(f"    python3 scripts/setup.py --registry {args.registry}")
        print()
        return

    # ── export-tar ────────────────────────────────────────────────────────
    if args.action == "export-tar":
        if not args.out:
            log("--out required for export-tar  (e.g. --out /data/cwf_images.tar.gz)", "error")
            sys.exit(1)
        export_images_tar(images, args.out, args.dry_run)

        # Also bundle large files into the tar if they exist
        if not args.skip_files:
            existing_files = [
                REPO_ROOT / fdef["dest"]
                for fdef in files
                if (REPO_ROOT / fdef["dest"]).exists()
            ]
            if existing_files:
                bundle = args.out.with_name(args.out.stem + "_files.tar.gz")
                log(f"Bundling {len(existing_files)} large files → {bundle}", "info")
                if not args.dry_run:
                    with tarfile.open(bundle, "w:gz") as tf:
                        for fp in existing_files:
                            tf.add(fp, arcname=fp.relative_to(REPO_ROOT))
                    log(f"Files bundle: {bundle}  ({bundle.stat().st_size/1e9:.1f} GB)", "ok")
        return

    # ── import-tar ────────────────────────────────────────────────────────
    if args.action == "import-tar":
        if not args.archive_in:
            log("--in required for import-tar  (e.g. --in /data/cwf_images.tar.gz)", "error")
            sys.exit(1)
        import_images_tar(args.archive_in, args.dry_run)
        return


if __name__ == "__main__":
    main()
