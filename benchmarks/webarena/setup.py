#!/usr/bin/env python3
"""
benchmarks/webarena/setup.py — Fully Automated WebArena Setup for CWF.

This is the ONE script a manager needs to run. It handles EVERYTHING:
  1. System dependencies (Docker, iptables modules, Playwright libs)
  2. Python environment + packages (venv)
  3. Docker image download (tarballs) + load
  4. Container startup with correct port mappings
  5. Magento/GitLab/Wikipedia/Forum URL configuration
  6. Homepage Flask app
  7. Ollama LLM server installation + model pull
  8. WebArena repo clone + test data generation + auto-login cookies
  9. Validation (all services return 200)

GitLab is OPTIONAL and disabled by default (known IOError crash on RHEL9 overlay2).

Usage:
  python3 benchmarks/webarena/setup.py                    # full setup (no GitLab)
  python3 benchmarks/webarena/setup.py --host 10.45.154.35
  python3 benchmarks/webarena/setup.py --include-gitlab   # try GitLab (may fail)
  python3 benchmarks/webarena/setup.py --skip-docker      # if Docker already running
  python3 benchmarks/webarena/setup.py --skip-ollama      # if using external LLM
  python3 benchmarks/webarena/setup.py --model llama3:70b # Ollama model (default: 8b)
  python3 benchmarks/webarena/setup.py --dry-run          # print commands only
  python3 benchmarks/webarena/setup.py --images-dir /path # where .tar files are

Platform: CWF (Clearwater Forest) — CentOS/RHEL 9, no GPU, E-core Darkmont.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path

# If running from a potentially broken/missing venv, re-exec with system python3.
if (
    hasattr(sys, "real_prefix")  # virtualenv
    or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)  # venv
):
    # We're inside a venv. If the venv is broken or missing key files, re-exec with system python3.
    try:
        import importlib  # noqa: F401 — probe: test that venv is functional
    except ImportError:
        # Venv is broken. Re-exec with system python3.
        print(
            "[WARN] Running from a broken/incomplete venv. Re-launching with system python3...",
            file=sys.stderr,
        )
        os.execv("/usr/bin/python3", ["/usr/bin/python3", __file__] + sys.argv[1:])

# Suppress beartype PEP 585 deprecation warnings from third-party dependencies
# (gymnasium uses typing.Mapping[...] instead of collections.abc.Mapping[...]).
try:
    from beartype.roar import BeartypeDecorHintPep585DeprecationWarning
    warnings.filterwarnings("ignore", category=BeartypeDecorHintPep585DeprecationWarning)
except ImportError:
    pass

# WebArena itself requires Python 3.10+ at runtime, but the setup script
# can be run with Python 3.9 — it will install python3.11 via dnf and use that.
if sys.version_info < (3, 6):
    sys.exit(f"[ERROR] Python 3.6+ required to run setup. Current: {sys.version.split()[0]}")

# ── Constants ─────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# WebArena Docker image tarballs — download from CMU mirrors
WEBARENA_IMAGE_URLS = {
    "shopping": "http://metis.lti.cs.cmu.edu/webarena-images/shopping_final_0712.tar",
    "shopping_admin": "http://metis.lti.cs.cmu.edu/webarena-images/shopping_admin_final_0719.tar",
    "forum": "http://metis.lti.cs.cmu.edu/webarena-images/postmill-populated-exposed-withimg.tar",
    "gitlab": "http://metis.lti.cs.cmu.edu/webarena-images/gitlab-populated-final-port8023.tar",
    "wikipedia": "http://metis.lti.cs.cmu.edu/webarena-images/wikipedia_en_all_maxi_2022-05.zim",
}

WEBARENA_IMAGE_NAMES = {
    "shopping": "shopping_final_0712",
    "shopping_admin": "shopping_admin_final_0719",
    "forum": "postmill-populated-exposed-withimg",
    "gitlab": "gitlab-populated-final-port8023",
}

WEBARENA_PORTS = {
    "shopping": 7770,
    "shopping_admin": 7780,
    "forum": 9999,
    "gitlab": 8023,
    "wikipedia": 8888,
    "homepage": 4399,
}

# CentOS/RHEL packages for Playwright Chromium (playwright install-deps uses apt — fails on RHEL)
PLAYWRIGHT_CENTOS_PKGS = (
    "glib2 nss nspr atk at-spi2-atk cups-libs libdrm dbus-libs "
    "libxcb libxkbcommon libX11 libXcomposite libXdamage libXext "
    "libXfixes libXrandr mesa-libgbm pango cairo alsa-lib "
    "libxshmfence mesa-libEGL mesa-libGL libX11-xcb"
)

# iptables kernel modules required for Docker NAT on RHEL9
IPTABLES_MODULES = ["ip_tables", "iptable_nat", "iptable_filter", "ip_conntrack"]

WORKDIR = Path.home() / "cwf_agentic" / "webarena"
IMAGES_DIR_DEFAULT = Path.home() / "webarena_images"


# ── Utilities (shared across all benchmark setup.py scripts) ────────────────

sys.path.insert(0, str(REPO_ROOT))
from common.setup_utils import (  # noqa: E402
    banner, log, pip_install, run, run_capture, write_setup_marker,
)


def get_host_ip() -> str:
    """Auto-detect host IP from first non-loopback interface."""
    try:
        out = subprocess.run(
            "hostname -I | awk '{print $1}'",
            shell=True, capture_output=True, text=True
        ).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return "localhost"


def detect_os_family() -> str:
    """Returns 'centos' or 'ubuntu'."""
    try:
        with open("/etc/os-release") as f:
            text = f.read().lower()
        for centos_id in ("centos", "rhel", "fedora", "rocky", "almalinux"):
            if centos_id in text:
                return "centos"
        for ubuntu_id in ("ubuntu", "debian"):
            if ubuntu_id in text:
                return "ubuntu"
    except FileNotFoundError:
        pass
    if shutil.which("dnf") or shutil.which("yum"):
        return "centos"
    return "ubuntu"


# Intel corporate proxy — used on CWF lab machines when no proxy env vars are set.
_INTEL_PROXY = "http://proxy-dmz.intel.com:912"
_INTEL_NO_PROXY = "localhost,127.0.0.1,10.0.0.0/8,192.168.0.0/16,.intel.com"


def get_proxy_env() -> dict:
    """Get proxy environment variables if set, falling back to Intel corporate proxy."""
    proxy_vars = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                "http_proxy", "https_proxy", "no_proxy"):
        val = os.environ.get(key)
        if val:
            proxy_vars[key] = val
    # On Intel lab machines the proxy may not be in the environment (e.g. fresh root shell).
    # Fall back to the standard Intel DMZ proxy so that model pulls / curl installs work.
    if not proxy_vars.get("HTTPS_PROXY") and not proxy_vars.get("https_proxy"):
        proxy_vars["HTTP_PROXY"]  = _INTEL_PROXY
        proxy_vars["HTTPS_PROXY"] = _INTEL_PROXY
        proxy_vars["NO_PROXY"]    = _INTEL_NO_PROXY
        proxy_vars["http_proxy"]  = _INTEL_PROXY
        proxy_vars["https_proxy"] = _INTEL_PROXY
        proxy_vars["no_proxy"]    = _INTEL_NO_PROXY
    return proxy_vars


# ── Step 1: Docker + iptables ─────────────────────────────────────────────────

def setup_docker_and_iptables(os_family: str, dry_run: bool) -> None:
    banner("Step 1: Docker CE + iptables Kernel Modules")

    # Load iptables kernel modules (RHEL9 requires this for Docker NAT)
    log("Loading iptables kernel modules (required for Docker NAT on RHEL9)...")
    for mod in IPTABLES_MODULES:
        run(f"modprobe {mod}", dry_run=dry_run)

    # Persist modules across reboots
    if not dry_run:
        Path("/etc/modules-load.d/docker-nat.conf").write_text(
            "\n".join(IPTABLES_MODULES) + "\n"
        )
    log("iptables modules persisted to /etc/modules-load.d/docker-nat.conf", "ok")

    # Install Docker if not present
    if shutil.which("docker") and not dry_run:
        log("Docker already installed", "ok")
    else:
        if os_family == "centos":
            run("dnf install -y yum-utils", dry_run=dry_run)
            run("yum-config-manager --add-repo "
                "https://download.docker.com/linux/centos/docker-ce.repo",
                dry_run=dry_run)
            run("dnf install -y docker-ce docker-ce-cli containerd.io "
                "docker-buildx-plugin docker-compose-plugin",
                dry_run=dry_run)
        else:
            run("apt-get update -y && apt-get install -y "
                "docker-ce docker-ce-cli containerd.io "
                "docker-buildx-plugin docker-compose-plugin",
                dry_run=dry_run)

    # Configure Docker daemon (data-root on /root to use root partition)
    if not dry_run:
        Path("/etc/docker").mkdir(parents=True, exist_ok=True)
        # Create data-root BEFORE writing daemon.json — Docker load will fail
        # with "stat /root/docker-data/tmp: no such file or directory" otherwise.
        Path("/root/docker-data").mkdir(parents=True, exist_ok=True)
        Path("/etc/docker/daemon.json").write_text(json.dumps({
            "data-root": "/root/docker-data",
            "storage-driver": "overlay2",
            "iptables": True,
        }, indent=2) + "\n")
        log("Docker data-root created at /root/docker-data", "ok")

    # Configure Docker proxy (Intel network)
    proxy_env = get_proxy_env()
    if proxy_env:
        docker_proxy_dir = Path("/etc/systemd/system/docker.service.d")
        if not dry_run:
            docker_proxy_dir.mkdir(parents=True, exist_ok=True)
            lines = ["[Service]"]
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
                val = proxy_env.get(key) or proxy_env.get(key.lower())
                if val:
                    lines.append(f'Environment="{key}={val}"')
            (docker_proxy_dir / "proxy.conf").write_text("\n".join(lines) + "\n")
        log("Docker proxy configured for Intel network", "ok")

    run("systemctl daemon-reload", dry_run=dry_run)
    run("systemctl enable --now docker", dry_run=dry_run)
    log("Docker ready", "ok")


# ── Step 2: Playwright System Dependencies ────────────────────────────────────

def setup_playwright_deps(os_family: str, dry_run: bool) -> None:
    banner("Step 2: Playwright Chromium System Dependencies")

    if os_family == "centos":
        # playwright install-deps uses apt-get internally — fails on RHEL.
        # Install the libs manually via dnf.
        run(f"dnf install -y {PLAYWRIGHT_CENTOS_PKGS}", dry_run=dry_run)
        log("Playwright deps installed via dnf (RHEL workaround)", "ok")
    else:
        run("apt-get install -y "
            "libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 "
            "libcups2 libdrm2 libdbus-1-3 libxcb1 libxkbcommon0 "
            "libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 "
            "libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2",
            dry_run=dry_run)
        log("Playwright deps installed via apt", "ok")


# ── Step 3: Python Environment ────────────────────────────────────────────────

def setup_python_env(dry_run: bool) -> str:
    """Create venv and install WebArena deps. Returns venv path string."""
    banner("Step 3: Python Virtual Environment + WebArena Packages")

    venv_path = Path.home() / "webarena_venv"

    # Find Python 3.10+
    python_bin = None
    for candidate in ("python3.11", "python3.10", "python3"):
        if shutil.which(candidate):
            # Verify version
            ver = run_capture(f"{candidate} --version")
            if "3.10" in ver or "3.11" in ver or "3.12" in ver:
                python_bin = candidate
                break

    if python_bin is None:
        log("No Python 3.10+ found. Installing python3.11...", "info")
        run("dnf install -y python3.11 python3.11-devel 2>/dev/null || "
            "apt-get install -y python3.11 python3.11-dev",
            dry_run=dry_run)
        python_bin = "python3.11"

    if not venv_path.exists() or dry_run:
        run(f"{python_bin} -m venv {venv_path}", dry_run=dry_run)

    pip = str(venv_path / "bin" / "pip")

    run(f"{pip} install --upgrade pip setuptools wheel", dry_run=dry_run)
    webarena_pkgs = [
        "gymnasium",
        "playwright==1.32.1",
        "Pillow>=9.0",
        "evaluate",
        "openai==0.27.0",
        "types-tqdm",
        "tiktoken",
        "aiolimiter",
        "beartype==0.12.0",
        "flask>=2.0",
        "nltk",
        "text-generation",
        "transformers>=4.33.2,<4.40",
    ]
    log(f"Installing {len(webarena_pkgs)} packages (skipping already-satisfied)...", "info")
    pip_install(pip, webarena_pkgs, dry_run)

    # Install playwright browser (chromium only — skip install-deps on RHEL, done in Step 2)
    # PLAYWRIGHT_BROWSERS_PATH is required on unsupported OS (RHEL/CentOS) so the browser
    # binary lands in a known location rather than the default ~/.cache path.
    import os as _os
    pw_env = _os.environ.copy()
    pw_env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".playwright-browsers"))
    if dry_run:
        log(f"[dry-run] {venv_path}/bin/playwright install chromium", "info")
    else:
        pw_result = subprocess.run(
            [f"{venv_path}/bin/playwright", "install", "chromium"],
            env=pw_env,
        )
        if pw_result.returncode != 0:
            log("playwright install chromium failed — browser may not work", "warn")
        else:
            log("Playwright Chromium browser installed", "ok")

    log(f"Python venv ready at {venv_path}", "ok")
    return str(venv_path)


# ── Step 4: Clone WebArena Repo ───────────────────────────────────────────────

def clone_webarena(venv_path: str, dry_run: bool) -> Path:
    banner("Step 4: Clone WebArena Repository + Patch for Local Models")

    if WORKDIR.exists() and (WORKDIR / "run.py").exists():
        log(f"WebArena already cloned at {WORKDIR}", "ok")
    else:
        WORKDIR.parent.mkdir(parents=True, exist_ok=True)
        run(f"git clone https://github.com/web-arena-x/webarena.git {WORKDIR}",
            dry_run=dry_run)

    # Install in editable mode
    venv_pip = str(Path(venv_path) / "bin" / "pip")
    run(f"{venv_pip} install -e {WORKDIR}", dry_run=dry_run)

    # Patch tokenizer to handle non-OpenAI model names (Ollama/local models).
    # Uses regex to be indentation-agnostic — the upstream file may vary.
    tokenizer_file = WORKDIR / "llms" / "tokenizers.py"
    if tokenizer_file.exists() and not dry_run:
        import re
        content = tokenizer_file.read_text()
        # Match the assignment line regardless of leading whitespace, but only
        # if it is NOT already inside a try/except block.
        pattern = re.compile(
            r'^( +)(self\.tokenizer = tiktoken\.encoding_for_model\(model_name\))\s*$',
            re.MULTILINE,
        )
        if pattern.search(content) and "except KeyError" not in content:
            def _wrap_in_try(m):
                indent = m.group(1)
                return (
                    f"{indent}try:\n"
                    f"{indent}    self.tokenizer = tiktoken.encoding_for_model(model_name)\n"
                    f"{indent}except KeyError:\n"
                    f'{indent}    self.tokenizer = tiktoken.get_encoding("cl100k_base")'
                )
            content = pattern.sub(_wrap_in_try, content)
            tokenizer_file.write_text(content)
            log("Patched tokenizers.py for local model compatibility", "ok")
        else:
            log("tokenizers.py already patched or pattern not matched", "ok")

    # Patch 2: ZeroDivisionError in upstream run.py when all tasks fail
    # (scores list is empty → division by zero on line: sum(scores)/len(scores))
    upstream_run = WORKDIR / "run.py"
    if upstream_run.exists() and not dry_run:
        content = upstream_run.read_text()
        old = 'logger.info(f"Average score: {sum(scores) / len(scores)}")'
        new = ('logger.info(f"Average score: {sum(scores) / len(scores) if scores else 0.0}")')
        if old in content and new not in content:
            upstream_run.write_text(content.replace(old, new))
            log("Patched run.py: ZeroDivisionError when scores list is empty", "ok")

    # Patch 3: upstream evaluator hardcodes gpt-4-1106-preview for fuzzy/ua match.
    # Replace with llama3.1:70b via WEBARENA_EVAL_MODEL env var (falls back to
    # gpt-4-1106-preview if not set, preserving original behaviour).
    helper_file = WORKDIR / "evaluation_harness" / "helper_functions.py"
    if helper_file.exists() and not dry_run:
        import re as _re
        content = helper_file.read_text()
        # Replace hardcoded model string with env-var lookup in both llm_fuzzy_match
        # and llm_ua_match (both use the same pattern)
        patched = _re.sub(
            r'model="gpt-4-1106-preview"',
            'model=__import__("os").environ.get("WEBARENA_EVAL_MODEL", "gpt-4-1106-preview")',
            content,
        )
        if patched != content:
            helper_file.write_text(patched)
            log("Patched helper_functions.py: evaluator model reads WEBARENA_EVAL_MODEL env var", "ok")
        else:
            log("helper_functions.py already patched or pattern not matched", "ok")

    log(f"WebArena repo ready at {WORKDIR}", "ok")
    return WORKDIR


# ── Step 5: Download + Load Docker Images ─────────────────────────────────────

def download_and_load_images(images_dir: Path, include_gitlab: bool,
                             dry_run: bool) -> None:
    banner("Step 5: Download + Load WebArena Docker Images")

    images_dir.mkdir(parents=True, exist_ok=True)

    services = ["shopping", "shopping_admin", "forum", "wikipedia"]
    if include_gitlab:
        services.append("gitlab")

    for svc in services:
        url = WEBARENA_IMAGE_URLS[svc]
        filename = url.split("/")[-1]
        filepath = images_dir / filename

        # Download if not already present
        if not filepath.exists() or dry_run:
            log(f"Downloading {svc}: {filename} ...", "info")
            run(f"wget -c -q --show-progress '{url}' -O {filepath}",
                dry_run=dry_run, timeout=7200)
        else:
            log(f"{svc}: {filename} already exists, skipping download", "ok")

        # Load Docker images (not for .zim files)
        if svc != "wikipedia":
            image_name = WEBARENA_IMAGE_NAMES[svc]
            # Check if already loaded
            already_loaded = run_capture(f"docker images -q {image_name}", dry_run=dry_run)
            if already_loaded:
                log(f"{svc}: image {image_name} already loaded", "ok")
            else:
                log(f"Loading {svc} into Docker...", "info")
                result = run(f"docker load --input {filepath}", dry_run=dry_run, timeout=600)
                if not dry_run and result.returncode != 0:
                    log(
                        f"[FATAL] docker load failed for {svc} (exit {result.returncode}).\n"
                        f"  Common cause: /root/docker-data did not exist when Docker started.\n"
                        f"  Fix: mkdir -p /root/docker-data && systemctl restart docker\n"
                        f"  Then re-run: python3 benchmarks/webarena/setup.py --skip-docker --skip-ollama",
                        "error",
                    )
                    sys.exit(1)
                # Verify image is now visible
                if not dry_run:
                    loaded_check = run_capture(f"docker images -q {image_name}")
                    if not loaded_check:
                        log(
                            f"[FATAL] docker load reported success but image '{image_name}' not found.\n"
                            f"  Check Docker data-root: docker info | grep 'Docker Root Dir'",
                            "error",
                        )
                        sys.exit(1)
                log(f"{svc}: image {image_name} loaded successfully", "ok")

    log("All Docker images ready", "ok")


# ── Step 6: Start Containers + Configure URLs ─────────────────────────────────

def start_and_configure_services(host: str, images_dir: Path,
                                  include_gitlab: bool, dry_run: bool) -> None:
    banner("Step 6: Start Containers + Configure Service URLs")

    # Stop/remove any existing containers (handles both running and stopped)
    for name in ["shopping", "shopping_admin", "forum", "gitlab", "wikipedia"]:
        run(f"docker rm -f {name} 2>/dev/null || true", dry_run=dry_run)

    def _require_image(image_name: str) -> None:
        """Abort if a required Docker image is not loaded."""
        if dry_run:
            return
        if not run_capture(f"docker images -q {image_name}"):
            log(
                f"[FATAL] Docker image '{image_name}' not loaded.\n"
                f"  Run image load step first:\n"
                f"    python3 benchmarks/webarena/setup.py --skip-docker --skip-ollama --skip-containers\n"
                f"  Or load manually:\n"
                f"    docker load --input <path-to-{image_name}.tar>",
                "error",
            )
            sys.exit(1)

    # ── Start Shopping
    _require_image("shopping_final_0712")
    run("docker run --name shopping -p 7770:80 -d shopping_final_0712",
        dry_run=dry_run)

    # ── Start Shopping Admin
    _require_image("shopping_admin_final_0719")
    run("docker run --name shopping_admin -p 7780:80 -d shopping_admin_final_0719",
        dry_run=dry_run)

    # ── Start Forum (Reddit/Postmill)
    _require_image("postmill-populated-exposed-withimg")
    run("docker run --name forum -p 9999:80 -d postmill-populated-exposed-withimg",
        dry_run=dry_run)

    # ── Start GitLab (optional — known IOError issues on RHEL9)
    if include_gitlab:
        log("Starting GitLab (with tmpfs fix for prometheus mmap issue)...", "info")
        run("docker run --name gitlab -d -p 8023:8023 "
            "--tmpfs /var/opt/gitlab/gitlab-rails/shared/prometheus_multiproc_dir:exec,size=128M "
            "--shm-size=512m "
            "gitlab-populated-final-port8023 "
            "/opt/gitlab/embedded/bin/runsvdir-start",
            dry_run=dry_run)
    else:
        log("GitLab SKIPPED (use --include-gitlab to enable)", "info")

    # ── Start Wikipedia (kiwix)
    zim_file = images_dir / "wikipedia_en_all_maxi_2022-05.zim"
    if zim_file.exists() or dry_run:
        run(f"docker run -d --name=wikipedia "
            f"--volume={images_dir}:/data "
            f"-p 8888:80 "
            f"ghcr.io/kiwix/kiwix-serve:3.3.0 "
            f"wikipedia_en_all_maxi_2022-05.zim",
            dry_run=dry_run)
    else:
        log(f"Wikipedia .zim not found at {zim_file} — skipping", "warn")

    # ── Wait for MySQL inside shopping containers to initialize
    log("Waiting 2 minutes for Shopping/Shopping Admin MySQL to initialize...", "info")
    if not dry_run:
        time.sleep(120)

    # ── Configure Shopping base URLs
    log("Configuring Shopping store URL...", "info")
    run(f'docker exec shopping /var/www/magento2/bin/magento '
        f'setup:store-config:set --base-url="http://{host}:7770"',
        dry_run=dry_run)
    run(f"docker exec shopping mysql -h 127.0.0.1 -u magentouser -pMyPassword magentodb "
        f"-e \"UPDATE core_config_data SET value='http://{host}:7770/' "
        f"WHERE path='web/secure/base_url';\"",
        dry_run=dry_run)
    run("docker exec shopping /var/www/magento2/bin/magento cache:flush",
        dry_run=dry_run)

    # ── Configure Shopping Admin base URLs
    log("Configuring Shopping Admin store URL...", "info")
    run(f'docker exec shopping_admin /var/www/magento2/bin/magento '
        f'setup:store-config:set --base-url="http://{host}:7780"',
        dry_run=dry_run)
    run(f"docker exec shopping_admin mysql -h 127.0.0.1 -u magentouser -pMyPassword magentodb "
        f"-e \"UPDATE core_config_data SET value='http://{host}:7780/' "
        f"WHERE path='web/secure/base_url';\"",
        dry_run=dry_run)
    # Disable forced password reset (required for auto-login)
    run("docker exec shopping_admin php /var/www/magento2/bin/magento "
        "config:set admin/security/password_is_forced 0", dry_run=dry_run)
    run("docker exec shopping_admin php /var/www/magento2/bin/magento "
        "config:set admin/security/password_lifetime 0", dry_run=dry_run)
    run("docker exec shopping_admin /var/www/magento2/bin/magento cache:flush",
        dry_run=dry_run)

    # ── Configure GitLab (if enabled)
    if include_gitlab:
        log("Waiting 5 minutes for GitLab to fully boot...", "info")
        if not dry_run:
            time.sleep(300)
        run("docker exec gitlab update-permissions", dry_run=dry_run)
        run(f'docker exec gitlab sed -i '
            f"\"s|^external_url.*|external_url 'http://{host}:8023'|\" "
            f'/etc/gitlab/gitlab.rb', dry_run=dry_run)
        # Disable prometheus (prevents IOError unmapped file crash)
        disable_prom = (
            'docker exec gitlab bash -c "'
            "echo \\\"prometheus_monitoring['enable'] = false\\\" >> /etc/gitlab/gitlab.rb && "
            "echo \\\"sidekiq['metrics_enabled'] = false\\\" >> /etc/gitlab/gitlab.rb && "
            "echo \\\"puma['exporter_enabled'] = false\\\" >> /etc/gitlab/gitlab.rb"
            '"'
        )
        run(disable_prom, dry_run=dry_run)
        run("docker exec gitlab gitlab-ctl reconfigure", dry_run=dry_run, timeout=600)
        log("GitLab configured (prometheus disabled)", "ok")

    log("All containers started and configured", "ok")


# ── Step 7: Start Homepage Flask App ──────────────────────────────────────────

def start_homepage(host: str, venv_path: str, dry_run: bool) -> None:
    banner("Step 7: Start Homepage Flask App")

    homepage_dir = WORKDIR / "environment_docker" / "webarena-homepage"
    template = homepage_dir / "templates" / "index.html"

    if template.exists() and not dry_run:
        content = template.read_text()
        content = content.replace("<your-server-hostname>", host)
        template.write_text(content)

    flask_bin = str(Path(venv_path) / "bin" / "flask")
    log_file = Path.home() / "webarena_homepage.log"

    # Kill any existing flask on 4399
    run("pkill -f 'flask.*4399' 2>/dev/null || true", dry_run=dry_run)

    run(f"cd {homepage_dir} && nohup {flask_bin} run --host=0.0.0.0 --port=4399 "
        f"> {log_file} 2>&1 &", dry_run=dry_run)

    if not dry_run:
        time.sleep(3)
    log("Homepage started on port 4399", "ok")


# ── Step 8: Ollama LLM Server ─────────────────────────────────────────────────

def setup_ollama(model: str, dry_run: bool) -> None:
    banner(f"Step 8: Ollama LLM Server (model: {model})")

    # Install Ollama — pass proxy env so curl can reach the internet on Intel network
    proxy_env_for_curl = {**os.environ, **get_proxy_env()}
    if not shutil.which("ollama") or dry_run:
        if dry_run:
            log("[dry-run] curl -fsSL https://ollama.com/install.sh | sh", "info")
        else:
            result = subprocess.run(
                "curl -fsSL https://ollama.com/install.sh | sh",
                shell=True, env=proxy_env_for_curl,
            )
            if result.returncode != 0:
                log("Ollama install failed — check network/proxy", "warn")

    # Configure Ollama with proxy (required on Intel network for model pull)
    proxy_env = get_proxy_env()
    ollama_override_dir = Path("/etc/systemd/system/ollama.service.d")
    if not dry_run:
        ollama_override_dir.mkdir(parents=True, exist_ok=True)
        lines = ["[Service]"]
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
            val = proxy_env.get(key) or proxy_env.get(key.lower())
            if val:
                lines.append(f'Environment="{key}={val}"')
        lines.append('Environment="OLLAMA_HOST=0.0.0.0:11434"')
        lines.append('Environment="OLLAMA_NUM_PARALLEL=4"')
        (ollama_override_dir / "override.conf").write_text("\n".join(lines) + "\n")

    run("systemctl daemon-reload", dry_run=dry_run)
    # Always restart (not just enable) so the proxy env from override.conf takes effect.
    # 'enable --now' is a no-op when the service is already running.
    run("systemctl enable ollama", dry_run=dry_run)
    run("systemctl restart ollama", dry_run=dry_run)
    log("Ollama service restarted with proxy config", "ok")

    if not dry_run:
        time.sleep(5)

    # Pull model — with automatic fallback from llama3:Xb → llama3.1:Xb
    # (Ollama library retired the plain 'llama3' tag; 'llama3.1' is the current name)
    def _ollama_model_exists(name: str) -> bool:
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True
            )
            return name in result.stdout
        except Exception:
            return False

    def _pull_with_fallback(primary: str) -> str:
        """Pull *primary*; if not found, try llama3.1 variant. Returns final model name."""
        import re as _re
        # Build env with proxy so that ollama pull can reach the registry on Intel network
        pull_env = {**os.environ, **get_proxy_env()}
        log(f"Pulling Ollama model: {primary} (this may take several minutes)...", "info")
        result = subprocess.run(["ollama", "pull", primary], env=pull_env)
        if result.returncode == 0 and _ollama_model_exists(primary):
            return primary
        # Try llama3 → llama3.1 substitution
        fallback = _re.sub(r'^llama3:', 'llama3.1:', primary)
        if fallback != primary:
            log(f"'{primary}' not found in registry — trying fallback: {fallback}", "warn")
            result2 = subprocess.run(["ollama", "pull", fallback], env=pull_env)
            if result2.returncode == 0 and _ollama_model_exists(fallback):
                log(f"Pulled fallback model: {fallback}", "ok")
                return fallback
        log(
            f"[ERROR] Could not pull '{primary}' or '{fallback}'.\n"
            "  Check 'ollama list' on the host and re-run setup with\n"
            f"  --model <exact-tag>, e.g. --model llama3.1:70b",
            "warn",
        )
        return primary  # return original so caller can decide

    if dry_run:
        log(f"[dry-run] ollama pull {model}", "info")
        final_model = model
    else:
        final_model = _pull_with_fallback(model)

    log(f"Ollama ready with model: {final_model}", "ok")


# ── Step 9: Generate Test Data + Auto-Login ───────────────────────────────────

def generate_test_data_and_login(host: str, venv_path: str,
                                  include_gitlab: bool, dry_run: bool) -> None:
    banner("Step 9: Generate Test Configs + Auto-Login Cookies")

    python = str(Path(venv_path) / "bin" / "python")
    workdir = str(WORKDIR)

    # Set environment variables for WebArena scripts
    env = os.environ.copy()
    env["SHOPPING"] = f"http://{host}:7770"
    env["SHOPPING_ADMIN"] = f"http://{host}:7780/admin"
    env["REDDIT"] = f"http://{host}:9999"
    env["GITLAB"] = f"http://{host}:8023" if include_gitlab else "http://localhost:8023"
    env["MAP"] = f"http://{host}:3000"
    env["WIKIPEDIA"] = (
        f"http://{host}:8888/wikipedia_en_all_maxi_2022-05"
        f"/A/User:The_other_Kiwix_guy/Landing"
    )
    env["HOMEPAGE"] = "PASS"

    # CRITICAL: Bypass Intel corporate proxy for Playwright (Chromium).
    # The Intel proxy blocks requests to internal IPs (e.g. 10.x.x.x) with
    # HTTP 403 "Access Denied — proxy policy restriction".
    # Strip proxy vars and set NO_PROXY to cover all WebArena container IPs.
    for _pvar in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(_pvar, None)
    _no_proxy = "localhost,127.0.0.1,0.0.0.0,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    env["NO_PROXY"] = _no_proxy
    env["no_proxy"] = _no_proxy

    # Generate config files (812 tasks)
    log("Generating task config files...", "info")
    if not dry_run:
        subprocess.run(
            [python, "scripts/generate_test_data.py"],
            cwd=workdir, env=env
        )
        n_configs = len(list((WORKDIR / "config_files").glob("*.json")))
        log(f"Generated {n_configs} task config files", "ok")

    # Generate auto-login cookies via Playwright
    # MUST re-apply Magento settings first — the Docker image has a hardcoded
    # base_url from the original build environment, causing Magento to redirect
    # away from the login form.  password_is_forced=1 also redirects to a
    # password-change page so the "user name" placeholder never appears.
    # These commands are idempotent and take ~5s.
    log("Applying Magento admin settings (base_url + security) before auto-login...", "info")
    magento_cmds = [
        f'/var/www/magento2/bin/magento setup:store-config:set --base-url="http://{host}:7780"',
        f'mysql -h 127.0.0.1 -u magentouser -pMyPassword magentodb '
        f'-e "UPDATE core_config_data SET value=\'http://{host}:7780/\' '
        f'WHERE path=\'web/secure/base_url\';"',
        '/var/www/magento2/bin/magento config:set admin/security/password_is_forced 0',
        '/var/www/magento2/bin/magento config:set admin/security/password_lifetime 0',
        '/var/www/magento2/bin/magento cache:flush',
    ]
    for _cmd in magento_cmds:
        run(f"docker exec shopping_admin {_cmd}", dry_run=dry_run)
    log("Magento admin settings applied", "ok")

    log("Generating auto-login cookies (Playwright → .auth/)...", "info")
    if not dry_run:
        (WORKDIR / ".auth").mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [python, "browser_env/auto_login.py"],
            cwd=workdir, env=env
        )
        if result.returncode == 0:
            log("Auto-login cookies generated", "ok")
        else:
            log("Auto-login partially failed (GitLab down is expected if skipped)", "warn")

    # Write env file for future use by run.py
    env_file = Path.home() / ".cwf_webarena_env"
    _no_proxy_val = "localhost,127.0.0.1,0.0.0.0,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    if not dry_run:
        env_file.write_text(
            f'# WebArena — source this file before running evaluation\n'
            f'export SHOPPING="http://{host}:7770"\n'
            f'export SHOPPING_ADMIN="http://{host}:7780/admin"\n'
            f'export REDDIT="http://{host}:9999"\n'
            f'export GITLAB="http://{host}:8023"\n'
            f'export MAP="http://{host}:3000"\n'
            f'export WIKIPEDIA="http://{host}:8888/wikipedia_en_all_maxi_2022-05'
            f'/A/User:The_other_Kiwix_guy/Landing"\n'
            f'export HOMEPAGE="PASS"\n'
            f'export OPENAI_API_KEY="dummy"\n'
            f'export OPENAI_API_BASE="http://localhost:11434/v1"\n'
            f'# Bypass Intel corporate proxy for WebArena local container IPs\n'
            f'export NO_PROXY="{_no_proxy_val}"\n'
            f'export no_proxy="{_no_proxy_val}"\n'
            f'unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy\n'
        )
    log(f"Environment file written to {env_file}", "ok")


# ── Step 10: Validation ───────────────────────────────────────────────────────

def validate_services(host: str, include_gitlab: bool, dry_run: bool) -> bool:
    banner("Step 10: Service Health Check")

    if dry_run:
        log("[dry-run] Would validate all services", "info")
        return True

    import urllib.error
    import urllib.request

    services = [
        ("Shopping", 7770),
        ("ShopAdmin", 7780),
        ("Forum", 9999),
        ("Wikipedia", 8888),
        ("Homepage", 4399),
    ]
    if include_gitlab:
        services.append(("GitLab", 8023))

    # Per-service max wait in seconds - Magento boots slowly.
    service_timeouts = {
        "Shopping": 600,
        "ShopAdmin": 600,
        "Forum": 120,
        "Wikipedia": 120,
        "Homepage": 60,
        "GitLab": 300,
    }
    container_map = {
        "Shopping": "shopping",
        "ShopAdmin": "shopping_admin",
        "Forum": "forum",
        "Wikipedia": "wikipedia",
        "GitLab": "gitlab",
    }

    # Raise HTTPError for redirect responses instead of auto-following them.
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    all_ok = True
    poll_interval = 10

    for name, port in services:
        container_name = container_map.get(name)
        if container_name:
            status = run_capture(
                f"docker inspect -f '{{{{.State.Status}}}}' {container_name} 2>/dev/null"
            )
            if status and status != "running":
                log(
                    f"  {name:12s} ({port}): container '{container_name}' is '{status}' - "
                    f"check: docker logs {container_name}",
                    "error",
                )
                all_ok = False
                continue

        # Use localhost for Docker container health checks (ports are mapped to 127.0.0.1)
        url = f"http://localhost:{port}"
        start_time = time.time()
        max_wait = service_timeouts.get(name, 180)
        deadline = start_time + max_wait
        code = 0
        attempt = 0
        printed_header = False
        err_str = ""
        while time.time() < deadline:
            attempt += 1
            try:
                opener = urllib.request.build_opener(_NoRedirect())
                req = urllib.request.Request(url, method="GET")
                try:
                    resp = opener.open(req, timeout=5)
                    code = resp.getcode()
                except urllib.error.HTTPError as http_err:
                    code = http_err.code
                err_str = ""
                if code in (200, 302, 301, 403):
                    elapsed = int(time.time() - start_time)
                    log(f"  {name:12s} ({port}): HTTP {code} ✓ [{elapsed}s]", "ok")
                    break
                err_str = f"HTTP {code}"
            except Exception as e:
                code = 0
                err_str = f"{type(e).__name__}: {e}"
            
            elapsed = int(time.time() - start_time)
            if not printed_header:
                log(f"  {name:12s} ({port}): waiting for service to be ready ...", "info")
                printed_header = True
            print(f"  [{elapsed:3d}s] {name} not ready yet ({err_str}) — retrying ...",
                  flush=True)
            time.sleep(poll_interval)

        if code not in (200, 302, 301, 403):
            all_ok = False
            elapsed = int(time.time() - start_time)
            last_error = err_str or f"HTTP {code}"
            log(f"  {name:12s} ({port}): timed out after {elapsed}s (last error: {last_error})", "error")
            if container_name:
                log(f"  Last 20 lines of '{container_name}' logs:", "warn")
                os.system(f"docker logs --tail 20 {container_name} 2>&1 | sed 's/^/    /'")

    if all_ok:
        log("All services healthy!", "ok")
    else:
        log("Some services are down — check with: docker ps && docker logs <name>", "warn")

    return all_ok


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WebArena — Fully Automated Setup for CWF Baremetal",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="",
                        help="Server IP/hostname. Auto-detected if not set.")
    parser.add_argument("--include-gitlab", action="store_true", default=False,
                        help="Include GitLab (often fails on RHEL9 — disabled by default).")
    parser.add_argument("--skip-docker", action="store_true",
                        help="Skip Docker installation (if already running).")
    parser.add_argument("--skip-ollama", action="store_true",
                        help="Skip Ollama setup (if using external LLM server).")
    parser.add_argument("--skip-images", action="store_true",
                        help="Skip image download/load (if already loaded).")
    parser.add_argument("--skip-containers", action="store_true",
                        help="Skip container start/config (if already running).")
    parser.add_argument("--model", default="llama3.1:8b",
                        help="Ollama model to pull. E.g. llama3.1:8b, llama3.1:70b")
    parser.add_argument("--images-dir", default=str(IMAGES_DIR_DEFAULT),
                        help="Directory for Docker image tarballs / .zim file.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing.")
    parser.add_argument("--health-check-only", action="store_true",
                        help="Skip setup steps and run only Step 10 service validation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    host = args.host or get_host_ip()
    images_dir = Path(args.images_dir)
    os_family = detect_os_family()
    cwf_model = args.model.split(":")[-1]

    banner("WebArena — Fully Automated Setup for CWF Baremetal")
    print(f"  Host IP       : {host}")
    print(f"  OS Family     : {os_family}")
    print(f"  Images Dir    : {images_dir}")
    print(f"  Include GitLab: {args.include_gitlab}")
    print(f"  LLM Model     : {args.model}")
    print(f"  Dry Run       : {args.dry_run}")
    print()
    print("  NOTE: WebArena setup uses its own venv (~~/webarena_venv).")
    print("        conda is NOT required for WebArena.")
    print()

    if args.health_check_only:
        ok = validate_services(host, args.include_gitlab, args.dry_run)
        sys.exit(0 if ok else 1)

    # Step 1: Docker + iptables
    if not args.skip_docker:
        setup_docker_and_iptables(os_family, args.dry_run)

    # Step 2: Playwright system deps
    setup_playwright_deps(os_family, args.dry_run)

    # Step 3: Python environment
    venv_path = setup_python_env(args.dry_run)

    # Step 4: Clone WebArena repo + patch
    clone_webarena(venv_path, args.dry_run)

    # Step 5: Download + load Docker images
    if not args.skip_images:
        download_and_load_images(images_dir, args.include_gitlab, args.dry_run)

    # Step 6: Start containers + configure URLs
    if not args.skip_containers:
        start_and_configure_services(host, images_dir, args.include_gitlab,
                                      args.dry_run)

    # Step 7: Start homepage
    start_homepage(host, venv_path, args.dry_run)

    # Step 8: Ollama LLM
    if not args.skip_ollama:
        setup_ollama(args.model, args.dry_run)

    # Step 9: Generate test data + auto-login
    generate_test_data_and_login(host, venv_path, args.include_gitlab, args.dry_run)

    # Step 10: Validate
    validate_services(host, args.include_gitlab, args.dry_run)

    # ── Write activate script ─────────────────────────────────────────────────
    activate_script = Path.home() / "activate_webarena.sh"
    if not args.dry_run:
        activate_script.write_text(
            "#!/bin/bash\n"
            "# WebArena environment activation — generated by setup.py\n"
            "# Usage: source ~/activate_webarena.sh\n"
            f"if [ ! -d {venv_path} ]; then\n"
            f'  echo "[ERROR] WebArena venv not found at {venv_path}. Run setup first:"\n'
            f'  echo "        python3 benchmarks/webarena/setup.py"\n'
            f"  return 1\n"
            f"fi\n"
            f"source {Path.home()}/.cwf_webarena_env\n"
            f"source {venv_path}/bin/activate\n"
            f"cd {REPO_ROOT}\n"
            f'echo "[ OK ] WebArena env ready. Venv: {venv_path}"\n'
            f'echo "[ OK ] Working dir: {REPO_ROOT}"\n'
            f'echo "[ OK ] Upstream WebArena clone: {WORKDIR}"\n'
        )
        activate_script.chmod(0o755)
    log(f"Activation script written: {activate_script}", "ok")

    # ── Final summary ─────────────────────────────────────────────────────────
    banner("Setup Complete!")
    print("  Activate environment (do this once per shell session):")
    print("    source ~/activate_webarena.sh")
    print()
    print(f"  Smoke test (10 tasks) from the cloned WebArena dir ({WORKDIR}):")
    print("    python run.py \\")
    print("      --instruction_path agent/prompts/jsons/p_cot_id_actree_2s.json \\")
    print("      --test_start_idx 0 --test_end_idx 10 \\")
    print(f"      --provider openai --model {args.model} \\")
    print("      --temperature 0.1 --max_tokens 512 \\")
    print("      --result_dir results/run_01")
    print()
    print(f"  Smoke test (10 tasks) from this CWF repo root ({REPO_ROOT}):")
    print(f"    python3 benchmarks/webarena/run.py --model {cwf_model} --start-idx 0 --end-idx 10")
    print()
    print("  Full run (812 tasks) via CWF runner from repo root:")
    print(f"    python3 benchmarks/webarena/run.py --model {cwf_model} --collect-emon")
    print()

    # Write .setup_complete marker so run.py can verify setup was done
    if not args.dry_run:
        setup_marker = Path(__file__).resolve().parent / ".setup_complete"
        write_setup_marker(
            setup_marker, "WebArena",
            [f"Host: {host}", f"Model: {args.model}"],
        )

    log("WebArena setup complete!", "ok")
    print("\n[SUCCESS] WebArena setup complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
