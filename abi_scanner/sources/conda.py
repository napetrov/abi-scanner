"""Conda/Anaconda package source adapter."""

import subprocess
import json
from pathlib import Path
from typing import List, Optional

from .base import PackageSource


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
            )
    
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
            print(f"✓ {existing[0].name} already downloaded")
            return existing[0]
        
        # Search for the package to get exact build string
        spec = f"{self.channel}::{package_name}={version}"
        
        try:
            # Use micromamba download (faster, no env needed)
            # micromamba download -c <channel> <package>=<version> -p <output_dir>
            cmd = [
                self.executable,
                'download',
                '-c', self.channel,
                f"{package_name}={version}",
                '--dest-folder', str(output_dir),
            ]
            
            print(f"Downloading {spec}...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Find the downloaded file
            downloaded = list(output_dir.glob(f"{package_name}-{version}*.tar.bz2"))
            downloaded.extend(output_dir.glob(f"{package_name}-{version}*.conda"))
            
            if not downloaded:
                raise RuntimeError(f"Download succeeded but file not found in {output_dir}")
            
            return downloaded[0]
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to download {spec}:\n{e.stderr}"
            )
    
    def extract(self, package_file: Path, extract_dir: Path) -> Path:
        """Extract conda package (.tar.bz2 or .conda).
        
        .conda format is a zip with info/ and pkg/ subdirectories.
        .tar.bz2 is a tarball with flat structure.
        """
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        if package_file.suffix == '.conda':
            # New .conda format (zip-based)
            subprocess.run(
                ['unzip', '-q', str(package_file), '-d', str(extract_dir)],
                check=True
            )
            # Libraries are in pkg/ subdirectory
            pkg_dir = extract_dir / 'pkg'
            if pkg_dir.exists():
                return pkg_dir
        else:
            # Old .tar.bz2 format
            subprocess.run(
                ['tar', 'xjf', str(package_file), '-C', str(extract_dir)],
                check=True
            )
        
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
