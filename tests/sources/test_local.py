"""Tests for LocalSource adapter."""

import pytest
import tarfile
from pathlib import Path
from abi_scanner.sources.local import LocalSource


@pytest.fixture
def local_source():
    """Create LocalSource instance."""
    return LocalSource()


@pytest.fixture
def sample_tarball(tmp_path):
    """Create a sample .tar.bz2 package for testing."""
    # Create a fake package structure
    pkg_dir = tmp_path / 'fake-pkg'
    pkg_dir.mkdir()
    
    lib_dir = pkg_dir / 'lib'
    lib_dir.mkdir()
    (lib_dir / 'libtest.so.1.0').write_text('fake library')
    
    include_dir = pkg_dir / 'include'
    include_dir.mkdir()
    (include_dir / 'test.h').write_text('// header')
    
    # Create tarball
    tarball = tmp_path / 'fake-pkg-1.0.0.tar.bz2'
    with tarfile.open(tarball, 'w:bz2') as tar:
        tar.add(pkg_dir, arcname='.')
    
    return tarball


def test_local_source_download_file(local_source, sample_tarball, tmp_path):
    """Test downloading (copying) a local file."""
    output_dir = tmp_path / 'output'
    
    result = local_source.download(
        str(sample_tarball),
        '1.0.0',  # Version ignored
        output_dir
    )
    
    assert result.exists()
    assert result.name == sample_tarball.name
    assert result.parent == output_dir


def test_local_source_download_directory(local_source, tmp_path):
    """Test 'downloading' a directory (returns as-is)."""
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    (source_dir / 'test.txt').write_text('test')
    
    output_dir = tmp_path / 'output'
    
    result = local_source.download(
        str(source_dir),
        '1.0.0',
        output_dir
    )
    
    # Should return the source directory itself (no copy for directories)
    assert result == source_dir.resolve()


def test_local_source_download_nonexistent(local_source, tmp_path):
    """Test downloading non-existent file raises error."""
    with pytest.raises(FileNotFoundError):
        local_source.download(
            '/nonexistent/file.tar.bz2',
            '1.0.0',
            tmp_path
        )


def test_local_source_extract_tarball(local_source, sample_tarball, tmp_path):
    """Test extracting a .tar.bz2 package."""
    extract_dir = tmp_path / 'extracted'
    
    result = local_source.extract(sample_tarball, extract_dir)
    
    assert result == extract_dir
    assert (extract_dir / 'lib' / 'libtest.so.1.0').exists()
    assert (extract_dir / 'include' / 'test.h').exists()


def test_local_source_extract_directory(local_source, tmp_path):
    """Test extracting a directory (returns as-is)."""
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    
    result = local_source.extract(source_dir, tmp_path / 'extract')
    
    # Should return the directory itself (no extraction needed)
    assert result == source_dir


def test_local_source_find_libraries(local_source, tmp_path):
    """Test finding libraries in extracted directory."""
    # Create fake extracted package
    extract_dir = tmp_path / 'extracted'
    lib_dir = extract_dir / 'lib'
    lib_dir.mkdir(parents=True)
    
    (lib_dir / 'libtest.so.1.0').write_text('lib')
    (lib_dir / 'libtest.so.1').write_text('symlink')
    (lib_dir / 'libother.so').write_text('other')
    
    # Find all libraries
    libraries = local_source.find_libraries(extract_dir, '')
    assert len(libraries) == 3
    
    # Find filtered by name
    test_libs = local_source.find_libraries(extract_dir, 'test')
    assert len(test_libs) == 2
    assert all('test' in lib.name for lib in test_libs)


def test_local_source_find_headers(local_source, tmp_path):
    """Test finding header files."""
    # Create fake extracted package
    extract_dir = tmp_path / 'extracted'
    include_dir = extract_dir / 'include'
    include_dir.mkdir(parents=True)
    
    (include_dir / 'test.h').write_text('header')
    (include_dir / 'test.hpp').write_text('header')
    (extract_dir / 'other.h').write_text('not in include')  # Should be filtered out
    
    headers = local_source.find_headers(extract_dir)
    
    # Should only find headers in include/ directories
    assert len(headers) == 2
    assert all('/include/' in str(h) for h in headers)
