"""Tests for AptSource adapter (mock-based)."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from abi_scanner.sources.apt import AptSource


@pytest.fixture
def apt_source():
    """Create AptSource instance with test base URL."""
    return AptSource(base_url='https://example.com/repo')


def test_apt_source_init_with_base_url():
    """Test AptSource initialization with base URL."""
    source = AptSource(base_url='https://apt.repos.intel.com/oneapi')
    assert source.base_url == 'https://apt.repos.intel.com/oneapi'


def test_apt_source_init_no_base_url():
    """Test AptSource initialization without base URL."""
    source = AptSource()
    assert source.base_url is None


@patch('abi_scanner.sources.apt.urllib.request.urlretrieve')
def test_apt_source_download_construct_url(mock_retrieve, apt_source, tmp_path):
    """Test downloading with constructed URL from base_url."""
    mock_retrieve.return_value = None
    
    result = apt_source.download(
        'intel-oneapi-dal',
        '2025.9.0-957',
        tmp_path
    )
    
    # Check URL construction
    expected_filename = 'intel-oneapi-dal_2025.9.0-957_amd64.deb'
    expected_url = f'https://example.com/repo/{expected_filename}'
    
    mock_retrieve.assert_called_once()
    assert expected_url in str(mock_retrieve.call_args)
    assert result.name == expected_filename


@patch('abi_scanner.sources.apt.urllib.request.urlretrieve')
def test_apt_source_download_direct_url(mock_retrieve, apt_source, tmp_path):
    """Test downloading with direct URL."""
    mock_retrieve.return_value = None
    
    direct_url = 'https://example.com/packages/test_1.0_amd64.deb'
    
    result = apt_source.download(
        direct_url,
        '1.0',  # Version ignored for direct URLs
        tmp_path
    )
    
    # Should use the direct URL
    mock_retrieve.assert_called_once()
    assert direct_url in str(mock_retrieve.call_args)
    assert result.name == 'test_1.0_amd64.deb'


def test_apt_source_download_no_base_url_raises():
    """Test download without base_url and non-URL package name raises error."""
    source = AptSource()  # No base_url
    
    with pytest.raises(ValueError, match='base_url required'):
        source.download('intel-oneapi-dal', '2025.9.0', Path('/tmp'))


@patch('abi_scanner.sources.apt.urllib.request.urlretrieve')
def test_apt_source_download_cached(mock_retrieve, apt_source, tmp_path):
    """Test download skips if .deb already exists."""
    # Create existing .deb
    existing_deb = tmp_path / 'test_1.0_amd64.deb'
    existing_deb.write_text('existing')
    
    result = apt_source.download('test', '1.0', tmp_path)
    
    # Should not download (cached)
    assert not mock_retrieve.called
    assert result == existing_deb


@patch('abi_scanner.sources.apt.subprocess.run')
def test_apt_source_extract_with_dpkg(mock_run, apt_source, tmp_path):
    """Test extraction using dpkg-deb."""
    package_file = tmp_path / 'test.deb'
    package_file.write_text('fake deb')
    extract_dir = tmp_path / 'extracted'
    
    # Mock dpkg-deb availability
    mock_run.return_value = Mock(returncode=0)
    
    result = apt_source.extract(package_file, extract_dir)
    
    assert result == extract_dir
    # Should call dpkg-deb twice (check + extract)
    assert mock_run.call_count >= 1


@patch('abi_scanner.sources.apt.subprocess.run')
def test_apt_source_extract_fallback_ar(mock_run, apt_source, tmp_path):
    """Test extraction fallback to ar+tar when dpkg-deb unavailable."""
    package_file = tmp_path / 'test.deb'
    extract_dir = tmp_path / 'extracted'
    
    # Create minimal .deb structure (ar archive)
    import subprocess
    import tarfile
    
    # Create data.tar.gz with test content
    data_tar = tmp_path / 'data.tar.gz'
    test_file = tmp_path / 'test.txt'
    test_file.write_text('content')
    
    with tarfile.open(data_tar, 'w:gz') as tar:
        tar.add(test_file, arcname='test.txt')
    
    # Create .deb (ar archive)
    (tmp_path / 'debian-binary').write_text('2.0\n')
    subprocess.run(['ar', 'r', str(package_file), 'debian-binary', str(data_tar)], 
                   cwd=tmp_path, check=True, capture_output=True)
    
    # Mock dpkg-deb not available; simulate 'ar x' by creating data.tar.gz in cwd
    import shutil

    def mock_run_side_effect(*args, **kwargs):
        cmd = args[0]
        if 'dpkg-deb' in cmd:
            raise FileNotFoundError()
        if cmd[:2] == ['ar', 'x']:
            cwd = Path(kwargs['cwd'])
            shutil.copy2(data_tar, cwd / 'data.tar.gz')
            return Mock(returncode=0)
        return Mock(returncode=0)
    
    mock_run.side_effect = mock_run_side_effect
    
    result = apt_source.extract(package_file, extract_dir)
    
    # Should extract successfully with ar
    assert result == extract_dir


def test_apt_source_find_libraries(apt_source, tmp_path):
    """Test finding libraries in extracted .deb."""
    # Create fake .deb extraction structure
    usr_lib = tmp_path / 'usr' / 'lib' / 'x86_64-linux-gnu'
    usr_lib.mkdir(parents=True)
    (usr_lib / 'libdal.so.2').write_text('lib')
    (usr_lib / 'libdal.so.2.0.0').write_text('lib')
    
    opt_lib = tmp_path / 'opt' / 'intel' / 'lib'
    opt_lib.mkdir(parents=True)
    (opt_lib / 'libtbb.so.12').write_text('lib')
    
    # Find dal libraries
    libraries = apt_source.find_libraries(tmp_path, 'dal')
    assert len(libraries) == 2
    assert all('dal' in lib.name for lib in libraries)
    
    # Find all libraries
    all_libs = apt_source.find_libraries(tmp_path, '')
    assert len(all_libs) >= 3


def test_apt_source_find_headers(apt_source, tmp_path):
    """Test finding headers in extracted .deb."""
    # Create fake include directories
    usr_include = tmp_path / 'usr' / 'include'
    usr_include.mkdir(parents=True)
    (usr_include / 'dal.h').write_text('header')
    
    opt_include = tmp_path / 'opt' / 'intel' / 'include'
    opt_include.mkdir(parents=True)
    (opt_include / 'tbb').mkdir(parents=True)
    (opt_include / 'tbb' / 'tbb.h').write_text('header')
    
    headers = apt_source.find_headers(tmp_path)
    
    assert len(headers) >= 2
    assert all(h.suffix == '.h' for h in headers)
