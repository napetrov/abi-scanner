#!/usr/bin/env python3
# abi_tracker/scripts/package_manager.py
# Universal package downloader supporting APT, conda, PyPI

import os
import sys
import yaml
import subprocess
from pathlib import Path
from urllib.parse import urlparse

class PackageManager:
    def __init__(self, config_file):
        with open(config_file) as f:
            self.config = yaml.safe_load(f)
        
        self.library = self.config['library']
    
    def get_source_config(self, source):
        """Get configuration for a specific source"""
        if source not in self.config['sources']:
            raise ValueError(f"Unknown source: {source}")
        return self.config['sources'][source]
    
    def list_available_versions(self, source):
        """List all available versions for a source"""
        # TODO: implement per-source version discovery
        # For now, hardcode common versions
        return ['2025.0', '2025.1', '2025.2', '2025.4', '2025.5', 
                '2025.6', '2025.7', '2025.8', '2025.9', '2025.10']
    
    def download_package(self, source, version, package_type, output_dir):
        """Download a package"""
        source_config = self.get_source_config(source)
        
        if source == 'apt':
            return self._download_apt(source_config, version, package_type, output_dir)
        elif source == 'conda':
            return self._download_conda(source_config, version, package_type, output_dir)
        elif source == 'pypi':
            return self._download_pypi(source_config, version, package_type, output_dir)
        else:
            raise ValueError(f"Unsupported source: {source}")
    
    def _download_apt(self, config, version, pkg_type, output_dir):
        """Download from APT repository"""
        pkg_info = config['packages'].get(pkg_type)
        if not pkg_info:
            raise ValueError(f"Package type {pkg_type} not defined for APT")
        
        # Parse pattern (needs build number from repodata)
        # Simplified: assume pattern intel-oneapi-dal-{version}-{version}.{build}_amd64.deb
        # TODO: fetch actual build number from Packages file
        
        base_url = config['base_url']
        # Placeholder: user must provide build number or we fetch from repodata
        filename = pkg_info['pattern'].format(version=version, build='957')
        
        url = f"{base_url}/{filename}"
        output_file = Path(output_dir) / filename
        
        if output_file.exists():
            print(f"✓ {filename} already downloaded", file=sys.stderr)
            return str(output_file)
        
        print(f"Downloading {url}...", file=sys.stderr)
        subprocess.run(['wget', '-q', url, '-O', str(output_file)], check=True)
        
        return str(output_file)
    
    def _download_conda(self, config, version, pkg_type, output_dir):
        """Download from conda channel"""
        # Use conda/mamba to download
        channel = config['channel']
        
        output_file = Path(output_dir) / f"{self.library}-{version}.tar.bz2"
        
        if output_file.exists():
            print(f"✓ {self.library}-{version} already downloaded", file=sys.stderr)
            return str(output_file)
        
        # Use conda download or direct URL
        # TODO: implement conda package download
        print(f"Conda download not yet implemented", file=sys.stderr)
        return None
    
    def _download_pypi(self, config, version, pkg_type, output_dir):
        """Download from PyPI"""
        # Use pip download or direct from PyPI API
        # TODO: implement
        print(f"PyPI download not yet implemented", file=sys.stderr)
        return None
    
    def extract_package(self, source, package_file, extract_dir):
        """Extract a downloaded package"""
        Path(extract_dir).mkdir(parents=True, exist_ok=True)
        
        if source == 'apt':
            # dpkg -x for .deb
            subprocess.run(['dpkg', '-x', package_file, extract_dir], check=True)
        elif source == 'conda':
            # tar xjf for conda .tar.bz2
            subprocess.run(['tar', 'xjf', package_file, '-C', extract_dir], check=True)
        elif source == 'pypi':
            # unzip for .whl
            subprocess.run(['unzip', '-q', package_file, '-d', extract_dir], check=True)
    
    def find_libraries(self, extract_dir):
        """Find .so files in extracted package"""
        return list(Path(extract_dir).glob(f"**/lib{self.library}*.so*"))
    
    def find_headers(self, extract_dir):
        """Find header files in extracted package"""
        headers = []
        for ext in ['*.h', '*.hpp', '*.hxx']:
            headers.extend(Path(extract_dir).glob(f"**/{ext}"))
        return [h for h in headers if '/include/' in str(h)]

def main():
    if len(sys.argv) < 4:
        print("Usage: package_manager.py <config> <source> <version> <output_dir>", file=sys.stderr)
        sys.exit(1)
    
    config_file = sys.argv[1]
    source = sys.argv[2]
    version = sys.argv[3]
    output_dir = sys.argv[4]
    
    pm = PackageManager(config_file)
    
    # Download both runtime and devel if available
    source_config = pm.get_source_config(source)
    
    for pkg_type in source_config['packages'].keys():
        try:
            pkg_file = pm.download_package(source, version, pkg_type, output_dir)
            if pkg_file:
                print(f"Downloaded: {pkg_file}")
        except Exception as e:
            print(f"Failed to download {pkg_type}: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()
