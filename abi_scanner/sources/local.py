"""Local filesystem package source adapter."""

import shutil
from pathlib import Path
from typing import List

from .base import PackageSource, VersionInfo
from .utils import safe_extract_tar, safe_extract_zip


class LocalSource(PackageSource):
    """Adapter for local package files or directories.
    
    Supports:
    - .deb files
    - .tar.bz2 / .tar.gz / .conda packages
    - Pre-extracted directories
    
    Unlike other adapters, this one doesn't download anything, just wraps local paths.
    """

    def list_versions(self, _package: str, **_kwargs) -> List[VersionInfo]:
        """Local source has no version index; return empty list."""
        return []
    
    def download(self, package_name: str, version: str, output_dir: Path) -> Path:
        """'Download' (copy) a local package file.
        
        Args:
            package_name: Path to local package file (can be relative or absolute)
            version: Ignored (local files don't have version discovery)
            output_dir: Directory to copy package into
            
        Returns:
            Path to the copied package file in output_dir
        """
        source_path = Path(package_name).expanduser().resolve()
        
        if not source_path.exists():
            raise FileNotFoundError(f"Local package not found: {source_path}")
        
        if source_path.is_dir():
            # If it's a directory, assume it's pre-extracted
            # Just return the path (no copy needed)
            return source_path
        
        # Copy file to output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / source_path.name
        
        if output_file.exists() and output_file.samefile(source_path):
            # Already in the right place
            return output_file
        
        # Overwrite stale file or copy new file
        print(f"Copying {source_path.name}...")
        shutil.copy2(source_path, output_file)
        
        return output_file
    
    def extract(self, package_file: Path, extract_dir: Path) -> Path:
        """Extract a local package file.
        
        Detects format by extension and uses appropriate tool.
        If package_file is already a directory, returns it as-is.
        """
        if package_file.is_dir():
            # Already extracted
            return package_file
        
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        # Detect format by extension
        suffix = package_file.suffix.lower()
        
        if suffix == '.deb':
            import subprocess
            try:
                subprocess.run(
                    ['dpkg-deb', '-x', str(package_file), str(extract_dir)],
                    check=True,
                    capture_output=True
                )
            except FileNotFoundError as e:
                raise RuntimeError("dpkg-deb not found. Install dpkg.") from e
        
        elif suffix in ['.bz2', '.gz', '.xz'] or package_file.name.endswith('.tar.bz2'):
            import tarfile
            with tarfile.open(package_file) as tar:
                safe_extract_tar(tar, extract_dir)
        
        elif suffix == '.conda':
            import zipfile
            # .conda is a zip archive - extract safely
            with zipfile.ZipFile(package_file) as zf:
                safe_extract_zip(zf, extract_dir)
            
            # .conda format has pkg/ subdirectory - validate it
            pkg_dir = extract_dir / 'pkg'
            if pkg_dir.exists():
                pkg_dir = pkg_dir.resolve()
                if not str(pkg_dir).startswith(str(extract_dir.resolve())):
                    raise RuntimeError("Unsafe .conda package structure")
                return pkg_dir
        
        elif suffix == '.zip':
            import zipfile
            with zipfile.ZipFile(package_file) as zf:
                safe_extract_zip(zf, extract_dir)
        
        else:
            raise ValueError(f"Unsupported package format: {package_file.suffix}")
        
        return extract_dir
    
    def find_libraries(self, extract_dir: Path, package_name: str) -> List[Path]:
        """Find shared libraries in extracted directory.
        
        Searches recursively for .so* (Linux), .dylib (macOS), .dll (Windows).
        Optionally filters by package_name.
        """
        libraries = []
        
        # Search for all shared libraries
        libraries.extend(extract_dir.rglob('*.so*'))
        libraries.extend(extract_dir.rglob('*.dylib'))
        libraries.extend(extract_dir.rglob('*.dll'))
        
        # Filter by package name if provided
        if package_name:
            libraries = [
                lib for lib in libraries
                if package_name.lower() in lib.name.lower()
            ]
        
        return sorted(libraries)
    
    def find_headers(self, extract_dir: Path) -> List[Path]:
        """Find header files in extracted directory.
        
        Searches recursively for .h, .hpp, .hxx files.
        Filters for include/ directories to reduce noise.
        """
        headers = []
        
        for ext in ['*.h', '*.hpp', '*.hxx']:
            headers.extend(extract_dir.rglob(ext))
        
        # Filter for include/ directories (heuristic to reduce noise)
        headers = [h for h in headers if '/include/' in str(h) or '\\include\\' in str(h)]
        
        return sorted(headers)
