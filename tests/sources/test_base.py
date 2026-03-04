"""Tests for base PackageSource interface."""

import pytest
from pathlib import Path
from abi_scanner.sources.base import PackageSource, PackageMetadata


def test_package_metadata_creation():
    """Test PackageMetadata dataclass initialization."""
    metadata = PackageMetadata(
        name='test-package',
        version='1.0.0',
        source='CondaSource'
    )
    
    assert metadata.name == 'test-package'
    assert metadata.version == '1.0.0'
    assert metadata.source == 'CondaSource'
    assert metadata.download_path is None
    assert metadata.extract_path is None
    assert metadata.libraries == []
    assert metadata.headers == []


def test_package_metadata_with_paths():
    """Test PackageMetadata with file paths."""
    metadata = PackageMetadata(
        name='dal',
        version='2025.9.0',
        source='CondaSource',
        download_path=Path('/tmp/dal-2025.9.0.tar.bz2'),
        extract_path=Path('/tmp/extracted/dal'),
        libraries=[Path('/tmp/extracted/dal/lib/libdal.so')],
        headers=[Path('/tmp/extracted/dal/include/dal.h')]
    )
    
    assert metadata.download_path == Path('/tmp/dal-2025.9.0.tar.bz2')
    assert len(metadata.libraries) == 1
    assert len(metadata.headers) == 1


def test_package_source_is_abstract():
    """Test that PackageSource cannot be instantiated directly."""
    with pytest.raises(TypeError):
        PackageSource()


class DummySource(PackageSource):
    """Minimal concrete implementation for testing."""
    
    def download(self, package_name: str, version: str, output_dir: Path) -> Path:
        return output_dir / f"{package_name}-{version}.tar"
    
    def extract(self, package_file: Path, extract_dir: Path) -> Path:
        return extract_dir
    
    def find_libraries(self, extract_dir: Path, package_name: str):
        return []
    
    def find_headers(self, extract_dir: Path):
        return []


def test_package_source_get_package_no_extract(tmp_path):
    """Test get_package convenience method without extraction."""
    source = DummySource()
    
    metadata = source.get_package(
        'test-pkg',
        '1.0.0',
        tmp_path,
        extract=False
    )
    
    assert metadata.name == 'test-pkg'
    assert metadata.version == '1.0.0'
    assert metadata.download_path == tmp_path / 'downloads' / 'test-pkg-1.0.0.tar'
    assert metadata.extract_path is None
    assert metadata.libraries == []
    assert metadata.headers == []
