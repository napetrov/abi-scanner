"""Tests for CondaSource adapter (mock-based)."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from abi_scanner.sources.conda import CondaSource


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for all tests."""
    with patch('abi_scanner.sources.conda.subprocess.run') as mock:
        # Mock successful version check
        mock.return_value = Mock(returncode=0, stdout='micromamba 1.0.0')
        yield mock


def test_conda_source_init_default(mock_subprocess):
    """Test CondaSource initialization with defaults."""
    source = CondaSource()
    
    assert source.channel == 'conda-forge'
    assert source.executable == 'micromamba'
    
    # No availability check on init (deferred until download)
    mock_subprocess.assert_not_called()


def test_conda_source_init_custom_channel():
    """Test CondaSource with custom channel."""
    source = CondaSource(channel='intel')
    
    assert source.channel == 'intel'


def test_conda_source_download_missing_executable(tmp_path):
    """Test CondaSource raises error on download if executable not found."""
    source = CondaSource()
    with patch('abi_scanner.sources.conda.subprocess.run') as mock:
        mock.side_effect = FileNotFoundError()

        with pytest.raises(RuntimeError, match='micromamba not found'):
            source.download('test', '1.0.0', tmp_path)


@patch('abi_scanner.sources.conda.subprocess.run')
def test_conda_source_download(mock_run, tmp_path):
    """Test downloading a conda package."""
    # Mock successful version check
    mock_run.return_value = Mock(returncode=0)
    
    source = CondaSource()
    mock_run.reset_mock()
    
    # Mock download command
    def mock_download(*args, **kwargs):
        cmd = args[0]
        # Simulate package creation only for the actual download command
        if 'download' in cmd:
            fake_pkg = tmp_path / 'test-1.0.0-py310_0.tar.bz2'
            fake_pkg.write_text('fake package')
        return Mock(returncode=0, stdout='', stderr='')
    
    mock_run.side_effect = mock_download
    
    result = source.download('test', '1.0.0', tmp_path)
    
    # Should call micromamba download
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert 'micromamba' in call_args
    assert 'download' in call_args
    assert 'test=1.0.0' in call_args
    
    # Verify downloaded file
    assert result.exists()
    assert result.name.startswith('test-1.0.0')


@patch('abi_scanner.sources.conda.subprocess.run')
def test_conda_source_download_cached(mock_run, tmp_path):
    """Test download skips if package already exists."""
    # Mock version check
    mock_run.return_value = Mock(returncode=0)
    source = CondaSource()
    mock_run.reset_mock()
    
    # Create existing package
    existing_pkg = tmp_path / 'test-1.0.0-build.tar.bz2'
    existing_pkg.write_text('existing')
    
    result = source.download('test', '1.0.0', tmp_path)
    
    # Only availability check should run, no download command
    assert mock_run.call_count == 1
    assert '--version' in mock_run.call_args[0][0]
    assert result == existing_pkg


@patch('abi_scanner.sources.conda.subprocess.run')
def test_conda_source_extract_tar_bz2(mock_run, tmp_path):
    """Test extracting .tar.bz2 conda package."""
    # Mock version check
    mock_run.return_value = Mock(returncode=0)
    source = CondaSource()
    mock_run.reset_mock()
    
    package_file = tmp_path / 'test-1.0.0.tar.bz2'
    package_file.write_text('fake')
    extract_dir = tmp_path / 'extracted'
    
    result = source.extract(package_file, extract_dir)
    
    # Should call tar
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert 'tar' in call_args
    assert 'xjf' in call_args


def test_conda_source_find_libraries(tmp_path):
    """Test finding libraries in conda package."""
    with patch('abi_scanner.sources.conda.subprocess.run'):
        source = CondaSource()
    
    # Create fake conda package structure
    lib_dir = tmp_path / 'lib'
    lib_dir.mkdir()
    (lib_dir / 'libtest.so.1.0').write_text('lib')
    (lib_dir / 'libtest.so.1').write_text('symlink')
    (lib_dir / 'libother.so').write_text('other')
    
    libraries = source.find_libraries(tmp_path, 'test')
    
    assert len(libraries) == 2
    assert all('test' in lib.name for lib in libraries)


def test_conda_source_find_headers(tmp_path):
    """Test finding headers in conda package."""
    with patch('abi_scanner.sources.conda.subprocess.run'):
        source = CondaSource()
    
    # Create fake include directory
    include_dir = tmp_path / 'include'
    include_dir.mkdir()
    (include_dir / 'test.h').write_text('header')
    (include_dir / 'subdir').mkdir()
    (include_dir / 'subdir' / 'test2.hpp').write_text('header')
    
    headers = source.find_headers(tmp_path)
    
    assert len(headers) == 2
    assert all(h.suffix in ['.h', '.hpp'] for h in headers)
