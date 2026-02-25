"""APT/Debian package source adapter."""

import subprocess
from pathlib import Path
from typing import List, Optional
import gzip
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

from .base import PackageSource
from .utils import safe_extract_tar


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
        base = "/".join(url.split("/")[:3])  # https://host

        with urllib.request.urlopen(url, timeout=60) as resp:
            index_data = gzip.decompress(resp.read()).decode("utf-8", "ignore")

        for block in index_data.split("\n\n"):
            pm = re.search(r"^Package: (.+)$", block, re.M)
            vm = re.search(r"^Version: (.+)$", block, re.M)
            fm = re.search(r"^Filename: (.+)$", block, re.M)
            if pm and vm and fm:
                if pm.group(1).strip() == package_name and vm.group(1).strip() == version:
                    rel_path = fm.group(1).strip()
                    return f"{base}/{rel_path}"

        raise ValueError(
            f"Package {package_name}={version} not found in APT index {url}"
        )

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
            print(f"✓ {filename} already downloaded")
            return output_file
        
        # Download
        print(f"Downloading {url}...")
        try:
            urllib.request.urlretrieve(url, output_file)
            return output_file
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            raise RuntimeError(f"Failed to download {url}: {e}") from e
    
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
        
        import tempfile
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
