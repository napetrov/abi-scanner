"""APT/Debian package source adapter."""

import sys

import subprocess
from pathlib import Path
from typing import List, Optional
import gzip
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse, unquote as _url_unquote

from .base import PackageSource
from .utils import safe_extract_tar


import os
import tempfile
import time
import hashlib as _hashlib

_APT_CACHE_TTL = 3600  # 1 hour


def _fetch_apt_index(url: str) -> str:
    """Fetch and cache APT Packages.gz content. Cache TTL: 1 hour.

    Falls back to stale cache on network error.
    """
    cache_dir = Path(os.environ.get(
        "ABI_SCANNER_CACHE_DIR",
        str(Path.home() / ".cache" / "abi_scanner" / "apt")
    ))
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_key = _hashlib.md5(url.encode()).hexdigest()[:16]
    cache_file = cache_dir / f"{cache_key}.txt"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < _APT_CACHE_TTL:
            return cache_file.read_text(encoding="utf-8")

    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = gzip.decompress(resp.read()).decode("utf-8", "ignore")
    except Exception:
        # On network error, try stale cache
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
        raise

    tmp_fd, tmp_str = tempfile.mkstemp(dir=cache_file.parent, suffix='.tmp')
    tmp_path = Path(tmp_str)
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as tmp_file:
            tmp_fd = None  # fdopen takes ownership
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.replace(cache_file)  # atomic on POSIX
        tmp_path = None
    except Exception:
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise
    return data


def normalize_debian_version(ver: str) -> str:
    """Normalize a Debian version string to PEP 440.

    Handles the ``epoch:upstream-revision~distro`` format by:
    1. Dropping epoch (``N:``) prefix — rare in Intel repos.
    2. Stripping the distro suffix (``~22.04``, ``~u22.04``, etc.).
    3. Replacing ``-`` (Debian revision separator) with ``.``.

    Examples::

        "1.3.26241.67-803.126~22.04" → "1.3.26241.67.803.126"
        "23.43.27642.67-803.126~22.04" → "23.43.27642.67.803.126"
        "2025.0.0-1169"               → "2025.0.0.1169"
        "1:1.3.0-1~focal"             → "1.3.0.1"
    """
    # Preserve Debian epoch using PEP 440 epoch syntax (e.g. "1:2.0" -> "1!2.0")
    if ":" in ver:
        epoch, rest = ver.split(":", 1)
        if epoch.isdigit():
            ver = f"{int(epoch)}!{rest}"
        else:
            ver = rest
    # Strip only known distro/backport tails; preserve prerelease markers like ~rc1, ~beta1
    ver = re.sub(
        r"~(?:u?\d+(?:\.\d+)*|focal|jammy|noble|bookworm|bullseye|buster|bionic|xenial)$",
        "",
        ver,
    )
    # Debian revision: replace first '-' and any subsequent '-' with '.'
    ver = ver.replace("-", ".")
    return ver


class AptSource(PackageSource):
    """Adapter for APT repositories (.deb packages).
    
    Supports:
    - Intel APT repository (apt.repos.intel.com)
    - Ubuntu/Debian repositories
    - Direct .deb file URLs
    
    Note: Does NOT require apt/dpkg to be installed (uses direct HTTP + ar/tar).
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize APT source.
        
        Args:
            base_url: Base URL for APT repository (optional)
                     If None, package must be specified as full URL
        """
        self.base_url = base_url
        self._pending_sha256s: dict[str, str] = {}
    

    # Default Intel APT index URL
    INTEL_APT_BASE = "https://apt.repos.intel.com/oneapi"
    INTEL_APT_INDEX = "https://apt.repos.intel.com/oneapi/dists/all/main/binary-amd64/Packages.gz"

    def resolve_url(self, package_name: str, version: str,
                    index_url: Optional[str] = None) -> str:
        """Resolve the .deb download URL for a package/version from Packages.gz.

        Args:
            package_name: Exact Debian package name (e.g. intel-oneapi-ccl-2021.17)
            version: Exact version string (e.g. 2021.17.2-5)
            index_url: URL to Packages.gz; defaults to Intel APT index

        Returns:
            Full https:// URL to the .deb file

        Raises:
            ValueError: if package/version not found in index
            ValueError: if index_url is not https://
        """
        url = index_url or self.INTEL_APT_INDEX
        if not url.startswith("https://"):
            raise ValueError(f"Only https:// index URLs allowed, got: {url}")
        dists_idx = url.find("/dists/")
        if dists_idx == -1:
            raise ValueError(f"Invalid APT index URL (missing /dists/): {url}")
        base = url[:dists_idx]  # https://host/repo (e.g. .../oneapi)

        try:
            index_data = _fetch_apt_index(url)
        except urllib.error.HTTPError as e:
            raise ValueError(f"HTTP {e.code} fetching APT index: {url}") from e
        except urllib.error.URLError as e:
            raise ValueError(f"Network error fetching APT index: {e.reason}") from e
        except (OSError, gzip.BadGzipFile) as e:
            raise ValueError(f"Failed to decompress APT index {url}: {e}") from e

        for block in index_data.split("\n\n"):
            pm = re.search(r"^Package: (.+)$", block, re.M)
            vm = re.search(r"^Version: (.+)$", block, re.M)
            fm = re.search(r"^Filename: (.+)$", block, re.M)
            if pm and vm and fm:
                if pm.group(1).strip() == package_name and vm.group(1).strip() == version:
                    rel_path = fm.group(1).strip()
                    # Decode percent-encoding before validation to prevent %2e%2e bypass
                    rel_path_decoded = _url_unquote(rel_path)
                    if not re.match(r'^[a-zA-Z0-9_./+-]+$', rel_path_decoded) or '..' in rel_path_decoded:
                        raise ValueError(f"Suspicious rel_path in APT index: {rel_path!r}")
                    full_url = f"{base}/{rel_path}"
                    # Verify resulting URL still has the same host as base
                    if urlparse(full_url).netloc != urlparse(base).netloc:
                        raise ValueError(f"URL host mismatch after rel_path: {full_url}")
                    # Extract and store SHA256 for download verification (URL-bound)
                    sha256_m = re.search(r"^SHA256: (.+)$", block, re.M)
                    if sha256_m:
                        self._pending_sha256s[full_url] = sha256_m.group(1).strip()
                    else:
                        import warnings
                        warnings.warn(
                            f"No SHA256 checksum in APT index for {package_name}={version}. "
                            "Download will proceed unverified.",
                            UserWarning,
                            stacklevel=2,
                        )
                    return full_url

        raise ValueError(
            f"Package {package_name}={version} not found in APT index {url}"
        )


    def list_versions(self, pkg_pattern: str, index_url: Optional[str] = None) -> list:
        """Return sorted list of (version, filename) tuples for packages matching pkg_pattern.

        pkg_pattern: extended POSIX regex matching Debian package names.
        Returns list of (version_str, filename_str) sorted by version.
        """
        import re as _re
        url = index_url or self.INTEL_APT_INDEX
        if not url.startswith("https://"):
            raise ValueError(f"Only https:// index URLs allowed, got: {url}")
        try:
            index_data = _fetch_apt_index(url)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch APT index: {e}") from e

        pat = _re.compile(pkg_pattern)
        entries = []
        for block in index_data.split("\n\n"):
            pm = _re.search(r"^Package: (.+)$", block, _re.M)
            vm = _re.search(r"^Version: (.+)$", block, _re.M)
            fm = _re.search(r"^Filename: (.+)$", block, _re.M)
            if pm and vm and fm and pat.search(pm.group(1).strip()):
                entries.append((vm.group(1).strip(), fm.group(1).strip(), pm.group(1).strip()))

        from packaging.version import Version, InvalidVersion

        def _sort_key(t):
            norm = normalize_debian_version(t[0])
            try:
                return (0, Version(norm))
            except InvalidVersion:
                # Last-resort: pad numeric segments, placed after valid versions
                parts = re.split(r'[^0-9]+', norm)
                return (1, tuple(int(x) if x else 0 for x in parts))

        return sorted(entries, key=_sort_key)

    def download(self, package_name: str, version: str, output_dir: Path) -> Path:
        """Download .deb package.
        
        Args:
            package_name: Package name or full URL to .deb file
            version: Version (ignored if package_name is a URL)
            output_dir: Directory to save .deb file
            
        If package_name starts with http:// or https://, treats it as direct URL.
        Otherwise constructs URL from base_url + package pattern.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Parse package name
        if package_name.startswith(('http://', 'https://')):
            url = package_name
            filename = Path(package_name).name
        else:
            if not self.base_url:
                raise ValueError(
                    "base_url required when package_name is not a full URL"
                )
            
            # Validate base_url scheme (prevent file://, ftp://, etc.)
            parsed = urlparse(self.base_url)
            if parsed.scheme not in ('http', 'https'):
                raise ValueError(
                    f"Invalid base_url scheme '{parsed.scheme}'. "
                    f"Only http:// and https:// are supported."
                )
            
            # Construct filename (Intel pattern: intel-oneapi-{lib}-{version}_{version}.{build}_amd64.deb)
            # Simplified: assume build number is in version string
            filename = f"{package_name}_{version}_amd64.deb"
            url = f"{self.base_url.rstrip('/')}/{filename}"
        
        output_file = output_dir / filename
        
        # Check if already downloaded
        if output_file.exists():
            # If we have a pending SHA256 for this URL, verify before trusting cache
            pending = self._pending_sha256s.get(url)
            if pending:
                actual = _hashlib.sha256(output_file.read_bytes()).hexdigest()
                if actual != pending:
                    output_file.unlink(missing_ok=True)
                    # Fall through to re-download
                else:
                    self._pending_sha256s.pop(url, None)
                    print(f"✓ {filename} already downloaded (SHA256 verified)", file=sys.stderr)
                    return output_file
            else:
                print(f"✓ {filename} already downloaded", file=sys.stderr)
                return output_file
        
        # Download
        print(f"Downloading {url}...", file=sys.stderr)
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                deb_bytes = resp.read()
            output_file.write_bytes(deb_bytes)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            raise RuntimeError(f"Failed to download {url}: {e}") from e
        # Fix 4: Verify SHA256 if available (set by resolve_url, keyed by URL)
        sha256 = self._pending_sha256s.pop(url, None)
        if sha256:
            import hashlib
            actual = hashlib.sha256(deb_bytes).hexdigest()
            if actual != sha256:
                output_file.unlink(missing_ok=True)
                raise ValueError(
                    f"SHA256 mismatch for {url}: expected {sha256}, got {actual}"
                )
        return output_file
    
    def extract(self, package_file: Path, extract_dir: Path) -> Path:
        """Extract .deb package using dpkg-deb or ar+tar.
        
        Tries dpkg-deb first (if available), falls back to ar+tar.
        """
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        # Try dpkg-deb first (cleaner, preserves permissions)
        try:
            subprocess.run(
                ['dpkg-deb', '--version'],
                capture_output=True,
                check=True
            )
            # dpkg-deb available
            subprocess.run(
                ['dpkg-deb', '-x', str(package_file), str(extract_dir)],
                check=True,
                capture_output=True
            )
            return extract_dir
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Fall back to manual extraction
        
        # Fallback: manual extraction with ar + tar
        # .deb structure: ar archive with debian-binary, control.tar.*, data.tar.*
        # We only need data.tar.* (contains actual files)
        
        import tarfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Extract .deb with ar
            try:
                subprocess.run(
                    ['ar', 'x', str(package_file)],
                    cwd=tmpdir,
                    check=True,
                    capture_output=True
                )
            except FileNotFoundError:
                raise RuntimeError(
                    "Neither dpkg-deb nor ar found. Install binutils or dpkg."
                )
            
            # Find data.tar.* (data.tar.gz, data.tar.xz, etc.)
            data_tar = list(tmpdir.glob('data.tar.*'))
            if not data_tar:
                raise RuntimeError(f"No data.tar.* found in {package_file}")
            
            # Extract data.tar.* safely (prevent path traversal CVE-2007-4559)
            with tarfile.open(data_tar[0]) as tar:
                safe_extract_tar(tar, extract_dir)
        
        return extract_dir
    
    def find_libraries(self, extract_dir: Path, package_name: str) -> List[Path]:
        """Find shared libraries in extracted .deb.
        
        Debian packages typically install to:
        - /usr/lib/x86_64-linux-gnu/*.so*
        - /opt/intel/oneapi/*/lib/*.so*
        
        Returns absolute paths relative to extract_dir.
        """
        libraries = set()

        # Common library locations in .deb packages
        search_dirs = [
            extract_dir / 'usr' / 'lib',
            extract_dir / 'usr' / 'lib' / 'x86_64-linux-gnu',
            extract_dir / 'opt',
        ]

        pattern = f"*{package_name}*.so*" if package_name else "*.so*"

        for search_dir in search_dirs:
            if search_dir.exists():
                for lib in search_dir.rglob(pattern):
                    libraries.add(lib)

        return sorted(libraries)
    
    def find_headers(self, extract_dir: Path) -> List[Path]:
        """Find header files in extracted .deb.
        
        Headers are typically in:
        - /usr/include/**/*.h
        - /opt/intel/oneapi/*/include/**/*.h
        """
        headers = []
        
        search_dirs = [
            extract_dir / 'usr' / 'include',
            extract_dir / 'opt',
        ]
        
        for search_dir in search_dirs:
            if search_dir.exists():
                for ext in ['*.h', '*.hpp', '*.hxx']:
                    headers.extend(search_dir.rglob(ext))
        
        return sorted(headers)
