"""Tests for AptSource adapter (mock-based)."""

import pytest
from unittest.mock import Mock, patch
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


@patch('abi_scanner.sources.apt.urllib.request.urlopen')
def test_apt_source_download_construct_url(mock_urlopen, apt_source, tmp_path):
    """Test downloading with constructed URL from base_url."""
    mock_resp = Mock()
    mock_resp.read.return_value = b'fake deb content'
    mock_resp.__enter__ = Mock(return_value=mock_resp)
    mock_resp.__exit__ = Mock(return_value=False)
    mock_urlopen.return_value = mock_resp

    result = apt_source.download(
        'intel-oneapi-dal',
        '2025.9.0-957',
        tmp_path
    )

    # Check URL construction
    expected_filename = 'intel-oneapi-dal_2025.9.0-957_amd64.deb'
    expected_url = f'https://example.com/repo/{expected_filename}'

    mock_urlopen.assert_called_once()
    assert expected_url in str(mock_urlopen.call_args)
    assert result.name == expected_filename


@patch('abi_scanner.sources.apt.urllib.request.urlopen')
def test_apt_source_download_direct_url(mock_urlopen, apt_source, tmp_path):
    """Test downloading with direct URL."""
    mock_resp = Mock()
    mock_resp.read.return_value = b'fake deb content'
    mock_resp.__enter__ = Mock(return_value=mock_resp)
    mock_resp.__exit__ = Mock(return_value=False)
    mock_urlopen.return_value = mock_resp

    direct_url = 'https://example.com/packages/test_1.0_amd64.deb'

    result = apt_source.download(
        direct_url,
        '1.0',  # Version ignored for direct URLs
        tmp_path
    )

    # Should use the direct URL
    mock_urlopen.assert_called_once()
    assert direct_url in str(mock_urlopen.call_args)
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


# ──────────────────────────────────────────────────────────────────────────────
# Tests added for second-pass review fixes
# ──────────────────────────────────────────────────────────────────────────────

import gzip
import warnings as _warnings


def _make_packages_gz(entries: list[dict]) -> bytes:
    """Build a minimal Packages.gz with the given list of package dicts."""
    blocks = []
    for e in entries:
        lines = "\n".join(f"{k}: {v}" for k, v in e.items())
        blocks.append(lines)
    data = "\n\n".join(blocks) + "\n\n"
    return gzip.compress(data.encode())


def test_resolve_url_rejects_url_encoded_traversal():
    """Fix 1: %2e%2e in rel_path must be rejected after URL-decode."""
    pkg_gz = _make_packages_gz([{
        "Package": "evil",
        "Version": "1.0",
        "Filename": "pool/%2e%2e/evil.deb",
        "SHA256": "abc123",
    }])
    source = AptSource()
    with patch("abi_scanner.sources.apt._fetch_apt_index",
               return_value=gzip.decompress(pkg_gz).decode()):
        with pytest.raises(ValueError, match="Suspicious rel_path"):
            source.resolve_url(
                "evil", "1.0",
                index_url="https://example.com/apt/dists/all/main/binary-amd64/Packages.gz"
            )


def test_resolve_url_warns_on_missing_sha256():
    """Fix 2: missing SHA256 field must emit a UserWarning."""
    pkg_gz = _make_packages_gz([{
        "Package": "mypkg",
        "Version": "2.0",
        "Filename": "pool/main/m/mypkg/mypkg_2.0_amd64.deb",
        # No SHA256 field
    }])
    source = AptSource()
    with patch("abi_scanner.sources.apt._fetch_apt_index",
               return_value=gzip.decompress(pkg_gz).decode()):
        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            url = source.resolve_url(
                "mypkg", "2.0",
                index_url="https://example.com/apt/dists/all/main/binary-amd64/Packages.gz"
            )
            assert url.endswith("mypkg_2.0_amd64.deb")
            assert len(w) == 1
            assert "No SHA256" in str(w[0].message)


def test_download_sha256_mismatch_raises(tmp_path):
    """Fix 2: SHA256 mismatch must raise ValueError and delete file."""
    import urllib.request
    import io

    source = AptSource()
    source._pending_sha256s["https://example.com/pkg.deb"] = "deadbeef" * 8  # 64-char wrong hash

    fake_response = Mock()
    fake_response.read.return_value = b"not-the-real-content"
    fake_response.__enter__ = Mock(return_value=fake_response)
    fake_response.__exit__ = Mock(return_value=False)

    with patch("urllib.request.urlopen", return_value=fake_response):
        with pytest.raises(ValueError, match="SHA256 mismatch"):
            source.download("https://example.com/pkg.deb", "", tmp_path)


def test_safe_extract_tar_rejects_path_traversal(tmp_path):
    """Fix 5: path traversal in tar archive must raise RuntimeError."""
    import tarfile, io
    from abi_scanner.sources.utils import safe_extract_tar

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tf:
        info = tarfile.TarInfo(name="../../evil.txt")
        info.size = 5
        tf.addfile(info, io.BytesIO(b"evil!"))
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode='r:gz') as tf:
        with pytest.raises(RuntimeError, match="Path traversal"):
            safe_extract_tar(tf, tmp_path)
