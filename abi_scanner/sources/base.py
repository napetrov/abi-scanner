"""Base interface for package sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class PackageMetadata:
    """Metadata about a downloaded/extracted package."""
    
    name: str
    version: str
    source: str
    download_path: Optional[Path] = None
    extract_path: Optional[Path] = None
    libraries: List[Path] = None
    headers: List[Path] = None
    
    def __post_init__(self):
        if self.libraries is None:
            self.libraries = []
        if self.headers is None:
            self.headers = []


class PackageSource(ABC):
    """Abstract base class for package sources.
    
    Each source adapter (conda, apt, local) implements this interface.
    """
    
    @abstractmethod
    def download(self, package_name: str, version: str, output_dir: Path) -> Path:
        """Download a package to output_dir.
        
        Args:
            package_name: Name of the package (e.g., 'dal', 'tbb')
            version: Package version (e.g., '2025.9.0')
            output_dir: Directory to save downloaded package
            
        Returns:
            Path to the downloaded package file
            
        Raises:
            ValueError: If package or version not found
            RuntimeError: If download fails
        """
        pass
    
    @abstractmethod
    def extract(self, package_file: Path, extract_dir: Path) -> Path:
        """Extract a downloaded package.
        
        Args:
            package_file: Path to the package file
            extract_dir: Directory to extract into
            
        Returns:
            Path to the extraction root
            
        Raises:
            RuntimeError: If extraction fails
        """
        pass
    
    @abstractmethod
    def find_libraries(self, extract_dir: Path, package_name: str) -> List[Path]:
        """Find shared libraries (.so/.dylib/.dll) in extracted package.
        
        Args:
            extract_dir: Root directory of extracted package
            package_name: Package name for filtering (e.g., 'dal' -> 'libdal*.so*')
            
        Returns:
            List of paths to shared libraries
        """
        pass
    
    @abstractmethod
    def find_headers(self, extract_dir: Path) -> List[Path]:
        """Find header files in extracted package.
        
        Args:
            extract_dir: Root directory of extracted package
            
        Returns:
            List of paths to header files (.h, .hpp, .hxx)
        """
        pass
    
    def get_package(self, package_name: str, version: str, 
                    output_dir: Path, extract: bool = True) -> PackageMetadata:
        """Download and optionally extract a package (convenience method).
        
        Args:
            package_name: Name of the package
            version: Package version
            output_dir: Directory for downloads and extraction
            extract: Whether to extract after download (default True)
            
        Returns:
            PackageMetadata with populated paths and library/header lists
        """
        download_dir = output_dir / 'downloads'
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # Download
        package_file = self.download(package_name, version, download_dir)
        
        metadata = PackageMetadata(
            name=package_name,
            version=version,
            source=self.__class__.__name__,
            download_path=package_file,
        )
        
        if extract:
            extract_dir = output_dir / 'extracted' / f"{package_name}-{version}"
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            self.extract(package_file, extract_dir)
            metadata.extract_path = extract_dir
            
            # Find libraries and headers
            metadata.libraries = self.find_libraries(extract_dir, package_name)
            metadata.headers = self.find_headers(extract_dir)
        
        return metadata
