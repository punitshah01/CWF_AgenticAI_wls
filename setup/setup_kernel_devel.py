#!/usr/bin/env python3
from __future__ import annotations  # enables str | None syntax on Python 3.9
"""
setup_kernel_devel.py

Checks if kernel-devel (RHEL family) or linux-headers (Debian family) is installed
for the currently running kernel. If not installed, attempts to install it:

  - Standard RHEL/CentOS/Fedora  : dnf / yum
  - Standard Debian/Ubuntu       : apt-get
  - Intel Internal OS (DMR BKC)  : fetches the matching kernel-devel RPM from
      https://ubit-artifactory-or.intel.com/artifactory/linuxbkc-or-local/linux-stack-bkc-dmr/
    by traversing WW (Work Week) directories from latest to earliest until a
    match for the running kernel is found.

Internal OS detection: /etc/motd contains "WELCOME TO LINUX STACK FOR DMR"
"""

import re
import sys
import logging
import tempfile
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ARTIFACTORY_BASE_URL = (
    "https://ubit-artifactory-or.intel.com/artifactory/"
    "linuxbkc-or-local/linux-stack-bkc-dmr/"
)
MOTD_PATH = "/etc/motd"
INTERNAL_OS_MARKER = "WELCOME TO LINUX STACK FOR DMR"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML link parser helper
# ---------------------------------------------------------------------------

class _LinkParser(HTMLParser):
    """Collect all href values from an HTML page."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for key, val in attrs:
                if key == "href" and val:
                    self.links.append(val)


def _parse_links(html: str) -> list[str]:
    p = _LinkParser()
    p.feed(html)
    return p.links


# ---------------------------------------------------------------------------
# OS / family detection
# ---------------------------------------------------------------------------

def detect_os_family() -> str:
    """
    Return 'rhel', 'debian', or 'unknown'.
    Reads /etc/os-release; falls back to checking binary presence.
    """
    os_release = Path("/etc/os-release")
    if os_release.exists():
        info: dict[str, str] = {}
        for line in os_release.read_text().splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip().strip('"').lower()

        os_id      = info.get("ID", "")
        id_like    = info.get("ID_LIKE", "")

        rhel_ids   = {"rhel", "centos", "fedora", "rocky", "almalinux",
                      "ol", "scientific"}
        debian_ids = {"debian", "ubuntu", "linuxmint", "pop",
                      "elementary", "kali", "raspbian"}

        if os_id in rhel_ids or any(x in id_like for x in
                                    ("rhel", "fedora", "centos")):
            return "rhel"
        if os_id in debian_ids or "debian" in id_like:
            return "debian"

    # Binary fallback
    if Path("/usr/bin/dnf").exists() or Path("/usr/bin/yum").exists():
        return "rhel"
    if Path("/usr/bin/apt-get").exists():
        return "debian"

    return "unknown"


def read_motd() -> str:
    """Return the contents of /etc/motd (empty string if unreadable)."""
    try:
        return Path(MOTD_PATH).read_text(errors="replace")
    except OSError:
        return ""


def is_internal_os() -> bool:
    """Return True when /etc/motd contains the DMR marker string."""
    return INTERNAL_OS_MARKER.upper() in read_motd().upper()


def get_motd_ww_hint() -> str | None:
    """
    Parse a line like  'Version  : 2025ww50'  from /etc/motd and return
    the WW token (e.g. '2025ww50') for use as a priority hint.
    Returns None if no such line is found.
    """
    for line in read_motd().splitlines():
        # match  'Version  : 2025ww50'  or  'version: 2025WW50'  etc.
        m = re.search(r"version\s*:\s*(\d{4}ww\d+)", line, re.IGNORECASE)
        if m:
            return m.group(1).lower()   # normalise to lowercase: 2025ww50
    return None


def get_kernel_version() -> str:
    """Return the running kernel release string (uname -r)."""
    result = subprocess.run(
        ["uname", "-r"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def pkg_manager() -> str:
    """Return 'dnf' if available, else 'yum'."""
    return "dnf" if Path("/usr/bin/dnf").exists() else "yum"


# ---------------------------------------------------------------------------
# DMR BKC kernel version extraction
# ---------------------------------------------------------------------------

def parse_dmr_bkc_kernel_ver(kernel_ver: str) -> tuple[str, str] | None:
    """
    For an Intel DMR BKC kernel whose uname -r looks like:
        6.14.0-dmr.bkc.6.14.10.5.23.x86_64

    Extract the *RPM* version and release that Artifactory uses:
        version = "6.14.10.5"
        release = "23"

    Returns (bkc_version, release) or None if the string doesn't match
    the DMR BKC uname pattern.
    """
    # Pattern: <base>-dmr.bkc.<bkc_ver_4part>.<release>.<arch>
    m = re.search(
        r"-dmr\.bkc\.(\d+\.\d+\.\d+\.\d+)\.(\d+)\.(x86_64|aarch64|noarch)",
        kernel_ver, re.IGNORECASE
    )
    if m:
        return (m.group(1), m.group(2))   # e.g. ("6.14.10.5", "23")
    return None


# ---------------------------------------------------------------------------
# Installed-package checks
# ---------------------------------------------------------------------------

def is_kernel_devel_installed_rhel(kernel_ver: str) -> bool:
    """
    Check for a kernel-devel package for *kernel_ver* via rpm.
    Handles both standard 'kernel-devel' and Intel BKC 'kernel-dmr-bkc-devel'
    naming conventions.
    """
    # Strip trailing arch suffix from kernel_ver if present (e.g. .x86_64)
    ver_plain = re.sub(r"\.(x86_64|aarch64|noarch)$", "", kernel_ver)

    candidates = [
        f"kernel-devel-{ver_plain}",
        f"kernel-dmr-bkc-devel-{ver_plain}",
    ]

    # For DMR BKC kernels, also probe using the extracted BKC version
    # e.g. "6.14.0-dmr.bkc.6.14.10.5.23.x86_64" → "kernel-dmr-bkc-devel-6.14.10.5-23"
    bkc = parse_dmr_bkc_kernel_ver(kernel_ver)
    if bkc:
        bkc_ver, bkc_rel = bkc
        candidates += [
            f"kernel-dmr-bkc-devel-{bkc_ver}-{bkc_rel}",
            f"kernel-dmr-bkc-devel-{bkc_ver}",
        ]

    for pkg in candidates:
        r = subprocess.run(
            ["rpm", "-q", pkg],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            log.info("Found installed: %s", r.stdout.strip())
            return True

    # Broader check: any installed package whose name contains 'kernel' and
    # 'devel' — match against both the raw version and BKC version
    r = subprocess.run(
        ["rpm", "-qa", "--queryformat", "%{NAME}-%{VERSION}-%{RELEASE}\n"],
        capture_output=True, text=True
    )
    def _norm(s: str) -> str:
        return re.sub(r"[\-\.]", "_", s).lower()

    ver_norms = [_norm(ver_plain)]
    if bkc:
        ver_norms.append(_norm(f"{bkc[0]}-{bkc[1]}"))

    for line in r.stdout.splitlines():
        line_norm = _norm(line)
        if "kernel" in line_norm and "devel" in line_norm:
            if any(vn and vn in line_norm for vn in ver_norms):
                log.info("Found installed: %s", line.strip())
                return True
    return False


def is_kernel_headers_installed_debian(kernel_ver: str) -> bool:
    """Check for linux-headers-<ver> via dpkg."""
    pkg = f"linux-headers-{kernel_ver}"
    r = subprocess.run(
        ["dpkg", "-s", pkg],
        capture_output=True, text=True
    )
    if r.returncode == 0 and "Status: install ok installed" in r.stdout:
        log.info("Found installed: %s", pkg)
        return True
    return False


# ---------------------------------------------------------------------------
# Standard (non-internal) installation
# ---------------------------------------------------------------------------

def install_via_dnf_yum(kernel_ver: str) -> bool:
    """Install kernel-devel package using dnf or yum.

    For DMR BKC kernels the package is 'kernel-dmr-bkc-devel-<bkc_ver>-<release>'
    rather than the standard 'kernel-devel-<uname_ver>'.
    """
    pm  = pkg_manager()
    bkc = parse_dmr_bkc_kernel_ver(kernel_ver)

    # Build ordered list of candidate package specs to try
    candidates: list[str] = []
    if bkc:
        bkc_ver, bkc_rel = bkc
        candidates.append(f"kernel-dmr-bkc-devel-{bkc_ver}-{bkc_rel}")
        candidates.append(f"kernel-dmr-bkc-devel-{bkc_ver}")

    # Standard fallback (also useful for non-BKC RHEL kernels)
    ver_plain = re.sub(r"\.(x86_64|aarch64|noarch)$", "", kernel_ver)
    candidates.append(f"kernel-devel-{ver_plain}")

    for pkg in candidates:
        log.info("Trying: sudo %s install -y %s", pm, pkg)
        r = subprocess.run(["sudo", pm, "install", "-y", pkg])
        if r.returncode == 0:
            log.info("Installation successful (%s).", pkg)
            return True
        log.warning("%s install of '%s' failed (exit %d).", pm, pkg, r.returncode)

    log.error("All dnf/yum install attempts failed for kernel %s.", kernel_ver)
    return False


def install_via_apt(kernel_ver: str) -> bool:
    """Install linux-headers-<ver> using apt-get."""
    pkg = f"linux-headers-{kernel_ver}"
    log.info("Updating apt cache ...")
    subprocess.run(["sudo", "apt-get", "update", "-qq"])
    log.info("Installing %s via apt-get ...", pkg)
    r = subprocess.run(["sudo", "apt-get", "install", "-y", pkg])
    if r.returncode == 0:
        log.info("Installation successful.")
        return True
    log.error("apt-get install failed (exit %d).", r.returncode)
    return False


# ---------------------------------------------------------------------------
# Artifactory traversal helpers
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = 30) -> str | None:
    """
    Fetch *url* and return the response body as text.
    Returns None on any network / HTTP error.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "kernel-devel-installer/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        log.debug("HTTP %s for %s", exc.code, url)
    except urllib.error.URLError as exc:
        log.debug("URL error for %s: %s", url, exc.reason)
    except Exception as exc:  # noqa: BLE001
        log.debug("Unexpected error fetching %s: %s", url, exc)
    return None


def list_directory(url: str) -> list[str]:
    """
    Return href values found in an Artifactory HTML directory listing.
    Absolute links and parent-directory links ('..' / '?') are filtered out.
    """
    html = http_get(url)
    if html is None:
        return []
    links = _parse_links(html)
    clean = []
    for lnk in links:
        # skip query strings, absolute URLs, and up-directory links
        if lnk.startswith(("?", "http://", "https://", "/")):
            continue
        if lnk in ("../", ".."):
            continue
        clean.append(lnk)
    return clean


def sort_ww_dirs(dirs: list[str]) -> list[str]:
    """
    Sort Work-Week directory names in descending order (latest first).

    Supported formats (case-insensitive):
        2025ww50      ->  year=2025, week=50   ← Intel internal format
        WW2024.01     ->  year=2024, week=1
        WW24_01       ->  year=2024, week=1
        WW2401        ->  year=2024, week=1
        WW01          ->  week only (year=0)
    """
    def _key(d: str) -> tuple[int, int]:
        name = d.rstrip("/").lower()

        # ---- Format: 2025ww50  (YYYYwwWW) --------------------------------
        m = re.match(r"(\d{4})ww(\d{1,2})$", name)
        if m:
            return (int(m.group(1)), int(m.group(2)))

        # ---- Formats prefixed with 'ww' -----------------------------------
        # Strip leading 'ww'
        if name.startswith("ww"):
            tail = name[2:]
        else:
            tail = name

        # YYYY.WW or YYYY_WW or YYYY-WW
        m = re.match(r"(\d{2,4})[._-](\d{1,2})$", tail)
        if m:
            yr, wk = int(m.group(1)), int(m.group(2))
            if yr < 100:
                yr += 2000
            return (yr, wk)

        # YYYYWW  (6 digits, e.g. 202401)
        m = re.match(r"(\d{4})(\d{2})$", tail)
        if m:
            return (int(m.group(1)), int(m.group(2)))

        # WW only (2 digits)
        m = re.match(r"(\d{1,2})$", tail)
        if m:
            return (0, int(m.group(1)))

        return (0, 0)

    return sorted(dirs, key=_key, reverse=True)


def rpms_in_listing(links: list[str]) -> list[str]:
    """Filter a link list down to those that end with .rpm."""
    return [lnk for lnk in links if lnk.lower().endswith(".rpm")]


# ---------------------------------------------------------------------------
# Kernel-version matching
# ---------------------------------------------------------------------------

def rpm_matches_kernel(rpm_name: str, kernel_ver: str) -> bool:
    """
    Return True when *rpm_name* is a kernel-devel RPM for *kernel_ver*.

    Handles both standard and Intel BKC naming:
        kernel-devel-<ver>.x86_64.rpm
        kernel-dmr-bkc-devel-<ver>.x86_64.rpm

    uname -r   →  RPM filename
    -------------------------------------------------------------------------------------
    6.14.0-dmr.bkc.6.14.10.5.23.x86_64  →  kernel-dmr-bkc-devel-6.14.10.5-23.el10.x86_64.rpm
    5.15.119-intel-next-230606T082947Z    →  kernel-devel-5.15.119-intel-next-...x86_64.rpm
    6.1.79.intel.12                       →  kernel-devel-6.1.79.intel.12-1.x86_64.rpm
    """
    name_lower = rpm_name.lower()

    # Must be some kind of kernel-*-devel package
    if not re.search(r"kernel[_-].*devel", name_lower):
        return False

    def _norm(s: str) -> str:
        """Collapse hyphens and dots to underscores for fuzzy comparison."""
        return re.sub(r"[\-\.]", "_", s).lower()

    # Strip trailing arch + .rpm so we only compare the version part
    rpm_bare = re.sub(r"\.(x86_64|aarch64|noarch)\.rpm$", "", rpm_name,
                      flags=re.IGNORECASE)
    rpm_norm = _norm(rpm_bare)

    # -----------------------------------------------------------------------
    # Strategy A: DMR BKC kernel
    #   uname -r  : 6.14.0-dmr.bkc.6.14.10.5.23.x86_64
    #   RPM has   : 6.14.10.5-23  (BKC version + release)
    # -----------------------------------------------------------------------
    bkc = parse_dmr_bkc_kernel_ver(kernel_ver)
    if bkc:
        bkc_ver, bkc_rel = bkc
        bkc_norm = _norm(f"{bkc_ver}-{bkc_rel}")   # e.g. "6_14_10_5_23"
        if bkc_norm in rpm_norm:
            return True
        # Version without release (looser match)
        if _norm(bkc_ver) in rpm_norm:
            return True

    # -----------------------------------------------------------------------
    # Strategy B: Standard kernel — full uname string in RPM name
    # -----------------------------------------------------------------------
    kv_clean = re.sub(r"\.(x86_64|aarch64|noarch)$", "", kernel_ver,
                      flags=re.IGNORECASE)
    kv_norm = _norm(kv_clean)
    if kv_norm and kv_norm in rpm_norm:
        return True

    # -----------------------------------------------------------------------
    # Strategy C: Version-prefix + release-prefix match
    #   e.g. kernel_ver="5.15.119-intel-next-230606..." → ver="5.15.119"
    # -----------------------------------------------------------------------
    parts    = kv_clean.split("-", 1)
    ver_part = _norm(parts[0])
    if ver_part and ver_part in rpm_norm:
        if len(parts) > 1:
            rel_prefix = _norm(parts[1][:15])
            if rel_prefix and rel_prefix in rpm_norm:
                return True
        else:
            return True

    return False


# ---------------------------------------------------------------------------
# Artifactory search
# ---------------------------------------------------------------------------

def _is_ww_dir(name: str) -> bool:
    """Return True if *name* looks like a Work-Week directory entry."""
    n = name.rstrip("/").lower()
    # 2025ww50  or  ww2024.01  or  ww24_01  etc.
    return bool(re.match(r"\d{4}ww\d+$", n) or re.match(r"ww\d", n))


def _scan_dir_for_rpm(base_url: str, kernel_ver: str,
                      depth: int = 2) -> str | None:
    """
    Recursively scan *base_url* up to *depth* directory levels deep.
    Returns the full URL of the first matching kernel-devel RPM, or None.

    Known actual layout:
        base/2025ww50/stack-bkc-cs10-dmr/x86_64/kernel-dmr-bkc-devel-*.rpm
    """
    links = list_directory(base_url)
    if not links:
        return None

    # Check RPMs at this level first
    for rpm in rpms_in_listing(links):
        if rpm_matches_kernel(rpm, kernel_ver):
            url = base_url.rstrip("/") + "/" + rpm
            log.info("Match found: %s", url)
            return url

    # Recurse into subdirectories (skip query-string and parent links)
    if depth > 0:
        sub_dirs = [
            link for link in links
            if link.endswith("/")
            and not link.startswith("?")
            and link not in ("../", "./")
        ]
        for sub in sub_dirs:
            sub_url = base_url.rstrip("/") + "/" + sub
            result  = _scan_dir_for_rpm(sub_url, kernel_ver, depth - 1)
            if result:
                return result

    return None


def find_kernel_devel_rpm_in_artifactory(
    kernel_ver: str,
    ww_hint: str | None = None,
) -> str | None:
    """
    Walk the Artifactory tree rooted at ARTIFACTORY_BASE_URL and return
    the *full URL* of the first kernel-devel RPM that matches *kernel_ver*.

    Actual layout:
        base/
          2025ww50/                  ← YYYYwwWW format
            stack-bkc-cs10-dmr/
              x86_64/
                kernel-dmr-bkc-devel-<ver>.x86_64.rpm

    If *ww_hint* (e.g. '2025ww50' parsed from /etc/motd) is provided it is
    tried first before falling back to all WW dirs sorted latest→earliest.
    """
    log.info("Fetching Artifactory base directory: %s", ARTIFACTORY_BASE_URL)
    base_links = list_directory(ARTIFACTORY_BASE_URL)

    if not base_links:
        log.error("Artifactory base directory is empty or unreachable.")
        return None

    # Identify WW-style directories and all other directories at base level
    ww_dirs   = sort_ww_dirs([link for link in base_links if _is_ww_dir(link)])
    root_rpms = rpms_in_listing(base_links)

    log.info("Found WW directories: %s", [d.rstrip("/") for d in ww_dirs])

    # Check root-level RPMs (edge case)
    for rpm in root_rpms:
        if rpm_matches_kernel(rpm, kernel_ver):
            return ARTIFACTORY_BASE_URL.rstrip("/") + "/" + rpm

    # Build ordered list of WW dirs to scan:
    #   1. hint WW (from motd) first if available and present in listing
    #   2. remaining WW dirs sorted latest → earliest
    ordered: list[str] = []
    if ww_hint:
        hint_norm = ww_hint.lower().rstrip("/") + "/"
        hint_norm_no_slash = hint_norm.rstrip("/")
        # Match regardless of trailing slash in listing
        matched = [
            d for d in ww_dirs
            if d.lower().rstrip("/") == hint_norm_no_slash
        ]
        if matched:
            ordered.extend(matched)
            log.info("Using motd WW hint: %s (priority)", hint_norm_no_slash)
        else:
            log.warning(
                "motd WW hint '%s' not found in Artifactory listing; "
                "scanning all WW dirs.", ww_hint
            )

    for d in ww_dirs:
        if d not in ordered:
            ordered.append(d)

    # Traverse each WW dir (up to 2 sub-levels deep to reach arch directories)
    for ww in ordered:
        ww_url = ARTIFACTORY_BASE_URL.rstrip("/") + "/" + ww.rstrip("/") + "/"
        log.info("Scanning WW directory: %s", ww_url)
        result = _scan_dir_for_rpm(ww_url, kernel_ver, depth=2)
        if result:
            return result

    log.warning("No matching kernel-devel RPM found for kernel %s", kernel_ver)
    return None


# ---------------------------------------------------------------------------
# RPM download + install
# ---------------------------------------------------------------------------

def download_rpm(url: str) -> Path | None:
    """Download an RPM to a temporary file, return its path."""
    filename = url.split("/")[-1]
    dest     = Path(tempfile.gettempdir()) / filename
    log.info("Downloading %s ...", url)
    try:
        urllib.request.urlretrieve(url, dest)
        log.info("Saved to %s (%d bytes)", dest, dest.stat().st_size)
        return dest
    except Exception as exc:  # noqa: BLE001
        log.error("Download failed: %s", exc)
        return None


def install_rpm_file(rpm_path: Path) -> bool:
    """Install a local RPM with rpm -ivh; fall back to dnf localinstall."""
    log.info("Installing %s ...", rpm_path.name)

    # Try rpm directly first
    r = subprocess.run(["sudo", "rpm", "-ivh", "--force", str(rpm_path)])
    if r.returncode == 0:
        log.info("Installed via rpm.")
        return True

    log.warning("rpm -ivh failed, trying %s localinstall ...", pkg_manager())
    r = subprocess.run(
        ["sudo", pkg_manager(), "localinstall", "-y", str(rpm_path)]
    )
    if r.returncode == 0:
        log.info("Installed via %s localinstall.", pkg_manager())
        return True

    log.error("All installation attempts failed for %s.", rpm_path.name)
    return False


def install_from_artifactory(kernel_ver: str,
                             ww_hint: str | None = None) -> bool:
    """
    Locate, download and install the kernel-devel RPM from Artifactory.
    Returns True on success.
    """
    rpm_url = find_kernel_devel_rpm_in_artifactory(kernel_ver, ww_hint=ww_hint)
    if not rpm_url:
        return False

    rpm_path = download_rpm(rpm_url)
    if not rpm_path:
        return False

    try:
        return install_rpm_file(rpm_path)
    finally:
        try:
            rpm_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    separator = "=" * 60
    log.info(separator)
    log.info("  Kernel Development Package Installer")
    log.info(separator)

    kernel_ver = get_kernel_version()
    log.info("Running kernel : %s", kernel_ver)

    os_family = detect_os_family()
    log.info("OS family      : %s", os_family)

    if os_family == "unknown":
        log.error("Cannot determine OS family (not RHEL-like or Debian-like).")
        sys.exit(1)

    internal = is_internal_os()
    ww_hint  = get_motd_ww_hint()
    if internal:
        log.info("Internal OS    : YES  (Intel DMR BKC detected via %s)", MOTD_PATH)
        if ww_hint:
            log.info("BKC WW hint    : %s  (from motd)", ww_hint)
    else:
        log.info("Internal OS    : no")

    # ------------------------------------------------------------------
    # 1. Already installed?
    # ------------------------------------------------------------------
    if os_family == "rhel":
        already_installed = is_kernel_devel_installed_rhel(kernel_ver)
    else:
        already_installed = is_kernel_headers_installed_debian(kernel_ver)

    if already_installed:
        log.info("kernel-devel / headers already present — nothing to do.")
        sys.exit(0)

    log.info("kernel-devel / headers NOT found for kernel %s.", kernel_ver)

    # ------------------------------------------------------------------
    # 2. Install
    # ------------------------------------------------------------------
    success = False

    if internal and os_family == "rhel":
        # -- Internal RHEL path: try Artifactory first ------------------
        log.info("Attempting installation from Intel Artifactory ...")
        success = install_from_artifactory(kernel_ver, ww_hint=ww_hint)

        if not success:
            log.warning(
                "Artifactory install failed. "
                "Falling back to %s ...", pkg_manager()
            )
            success = install_via_dnf_yum(kernel_ver)

    elif os_family == "rhel":
        success = install_via_dnf_yum(kernel_ver)

    else:  # debian
        success = install_via_apt(kernel_ver)

    # ------------------------------------------------------------------
    # 3. Report outcome
    # ------------------------------------------------------------------
    if success:
        log.info("kernel-devel / headers installation COMPLETED successfully.")
        sys.exit(0)
    else:
        log.error("Failed to install kernel-devel / headers.")
        sys.exit(1)


if __name__ == "__main__":
    main()
