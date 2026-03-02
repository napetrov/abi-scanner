"""Conda/Anaconda package source adapter."""

import subprocess
import json
import logging
import os
import shutil
from pathlib import Path
from typing import List

from .base import PackageSource, VersionInfo
from .utils import safe_extract_tar, safe_extract_zip

logger = logging.getLogger(__name__)


class CondaSource(PackageSource):
    """Adapter for conda/mamba/micromamba channels.
    
    Supports:
    - conda-forge
    - intel channel
    - Custom channels
    
    Uses micromamba for downloads (faster than conda, no environment needed).
    """
    
    def __init__(self, channel: str = 'conda-forge', executable: str = 'micromamba'):
        """Initialize conda source.
        
        Args:
            channel: Conda channel name (default: conda-forge)
            executable: Conda executable to use (micromamba/mamba/conda)
        """
        self.channel = channel
        self.executable = executable
    
    def _check_executable(self):
        """Verify that conda executable is available."""
        try:
            subprocess.run(
                [self.executable, '--version'],
                capture_output=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                f"{self.executable} not found. "
                f"Install it: https://mamba.readthedocs.io/en/latest/installation.html"
            ) from None
    

    def list_versions(self, package: str) -> List[VersionInfo]:
        """Return sorted list of available versions for a package on this channel.

        Uses micromamba search --json.
        Raises RuntimeError on tool/network failure; returns [] when package not found.
        """
        try:
            result = subprocess.run(
                [self.executable, "search", "-c", self.channel, package, "--json"],
                capture_output=True, text=True, check=False, timeout=60,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"micromamba executable not found: {self.executable!r}"
            ) from None
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"micromamba search timed out for {self.channel}:{package}"
            ) from None

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "PackagesNotFoundError" in stderr or "nothing provides" in stderr.lower():
                return []  # package genuinely absent from channel
            raise RuntimeError(
                f"micromamba search failed (rc={result.returncode}): {stderr[-300:]}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"micromamba search returned invalid JSON: {exc}") from exc

        versions = list({
            pkg["version"]
            for pkg in data.get("result", {}).get("pkgs", [])
        })
        from packaging.version import Version
        try:
            ordered = sorted(versions, key=lambda v: Version(v))
        except Exception:
            ordered = sorted(versions)

        return [VersionInfo(version=v) for v in ordered]

    def download(self, package_name: str, version: str, output_dir: Path) -> Path:
        """Download conda package.
        
        Uses micromamba to download .conda or .tar.bz2 package without installing.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Verify micromamba/mamba/conda is available only when needed
        self._check_executable()
        
        # Check if already downloaded
        # Conda packages: name-version-build.tar.bz2 or name-version-build.conda
        existing = list(output_dir.glob(f"{package_name}-{version}*.tar.bz2"))
        existing.extend(output_dir.glob(f"{package_name}-{version}*.conda"))
        
        if existing:
            newest = max(existing, key=lambda p: p.stat().st_mtime)
            print(f"✓ {newest.name} already downloaded")
            return newest
        
        # Search for the package to get exact build string
        spec = f"{self.channel}::{package_name}={version}"
        
        try:
            # Preferred path: micromamba download
            cmd = [
                self.executable,
                'download',
                '-c', self.channel,
                f"{package_name}={version}",
                '--dest-folder', str(output_dir),
            ]

            print(f"Downloading {spec}...")
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

        except subprocess.TimeoutExpired as e:
            logger.error("Timed out while downloading %s via `%s download`", spec, self.executable)
            raise RuntimeError(f"Timed out while downloading {spec}") from e

        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            # Fallback for older micromamba builds that do not support `download`
            if "arguments were not expected: download" not in stderr.lower():
                raise RuntimeError(f"Failed to download {spec}:\n{stderr}") from e

            mamba_root = output_dir / ".mamba_root"
            env_dir = output_dir / f".dl_env_{package_name}_{version}"
            mamba_root.mkdir(parents=True, exist_ok=True)

            fallback_cmd = [
                self.executable,
                'create',
                '-y',
                '--download-only',
                '-p', str(env_dir),
                '-c', self.channel,
                f"{package_name}={version}",
            ]
            try:
                fb = subprocess.run(
                    fallback_cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=300,
                    env={**os.environ, 'MAMBA_ROOT_PREFIX': str(mamba_root)}
                )
            except subprocess.TimeoutExpired as te:
                logger.error("Timed out while downloading %s via fallback create --download-only", spec)
                raise RuntimeError(
                    f"Timed out while downloading {spec} with fallback create --download-only"
                ) from te

            if fb.returncode != 0:
                raise RuntimeError(
                    f"Failed to download {spec} with fallback create --download-only:\n{(fb.stderr or '').strip()}"
                ) from e

            # Copy package file from mamba cache into output_dir
            pkgs_dir = mamba_root / 'pkgs'
            candidates = list(pkgs_dir.glob(f"{package_name}-{version}*.conda"))
            candidates.extend(pkgs_dir.glob(f"{package_name}-{version}*.tar.bz2"))
            if not candidates:
                raise RuntimeError(
                    f"Fallback download completed but package file not found in cache: {pkgs_dir}"
                ) from e

            src = max(candidates, key=lambda p: p.stat().st_mtime)
            dst = output_dir / src.name
            if not dst.exists():
                shutil.copy2(src, dst)

        # Find the downloaded file
        downloaded = list(output_dir.glob(f"{package_name}-{version}*.tar.bz2"))
        downloaded.extend(output_dir.glob(f"{package_name}-{version}*.conda"))

        if not downloaded:
            raise RuntimeError(f"Download succeeded but file not found in {output_dir}")

        return max(downloaded, key=lambda p: p.stat().st_mtime)
    
    def extract(self, package_file: Path, extract_dir: Path) -> Path:
        """Extract conda package (.tar.bz2 or .conda).
        
        .conda format is a zip with info/ and pkg/ subdirectories.
        .tar.bz2 is a tarball with flat structure.
        """
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        if package_file.suffix == '.conda':
            # New .conda format (zip container with nested pkg/info tarballs)
            import zipfile
            with zipfile.ZipFile(package_file) as zf:
                safe_extract_zip(zf, extract_dir)

            # Typical layout: pkg-*.tar.zst + info-*.tar.zst
            pkg_archives = sorted(extract_dir.glob('pkg-*.tar.*'))
            info_archives = sorted(extract_dir.glob('info-*.tar.*'))

            def _extract_nested(archive: Path, out_dir: Path):
                out_dir.mkdir(parents=True, exist_ok=True)
                # `tar --zstd` handles .tar.zst and also works for regular tar streams.
                # Fallback to Python tarfile for non-zstd archives.
                cmd = ['tar', '--extract', '--file', str(archive), '--directory', str(out_dir), '--zstd']
                run = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if run.returncode != 0:
                    import tarfile
                    with tarfile.open(archive) as tar:
                        safe_extract_tar(tar, out_dir)

            if pkg_archives:
                pkg_dir = extract_dir / 'pkg'
                _extract_nested(pkg_archives[-1], pkg_dir)
                return pkg_dir

            # Fallback: some producers may still place files directly
            if info_archives:
                info_dir = extract_dir / 'info'
                _extract_nested(info_archives[-1], info_dir)
            return extract_dir
        else:
            # Old .tar.bz2 format - extract safely
            import tarfile
            with tarfile.open(package_file) as tar:
                safe_extract_tar(tar, extract_dir)

        return extract_dir
    
    def find_libraries(self, extract_dir: Path, package_name: str) -> List[Path]:
        """Find shared libraries in conda package.
        
        Conda packages typically have libraries in:
        - lib/*.so (Linux)
        - lib/*.dylib (macOS)
        - Library/bin/*.dll (Windows)
        """
        libraries = []
        
        # Linux/macOS
        lib_dir = extract_dir / 'lib'
        if lib_dir.exists():
            libraries.extend(lib_dir.glob(f"lib{package_name}*.so*"))
            libraries.extend(lib_dir.glob(f"lib{package_name}*.dylib"))
        
        # Windows
        win_bin = extract_dir / 'Library' / 'bin'
        if win_bin.exists():
            libraries.extend(win_bin.glob(f"{package_name}*.dll"))
        
        return sorted(libraries)
    
    def find_headers(self, extract_dir: Path) -> List[Path]:
        """Find header files in conda package.
        
        Headers are typically in:
        - include/**/*.h
        - include/**/*.hpp
        """
        headers = []
        include_dir = extract_dir / 'include'
        
        if include_dir.exists():
            for ext in ['*.h', '*.hpp', '*.hxx']:
                headers.extend(include_dir.rglob(ext))
        
        return sorted(headers)
