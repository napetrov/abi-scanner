"""Utility functions for safe package extraction."""

from pathlib import Path
import tarfile
import zipfile


def safe_extract_tar(tar: tarfile.TarFile, extract_dir: Path):
    """Safely extract tar archive preventing path traversal (CVE-2007-4559).
    
    Args:
        tar: tarfile.TarFile object
        extract_dir: Destination directory
        
    Raises:
        RuntimeError: If any member attempts path traversal or is unsafe
    """
    extract_dir = extract_dir.resolve()
    
    for member in tar.getmembers():
        # Compute target path and resolve it
        member_path = (extract_dir / member.name).resolve()
        
        # Check path traversal
        if not str(member_path).startswith(str(extract_dir)):
            raise RuntimeError(
                f"Path traversal attempt detected: {member.name} "
                f"would extract outside {extract_dir}"
            )
        
        # Reject symlinks, hard links, device files
        if member.issym() or member.islnk():
            raise RuntimeError(
                f"Unsafe tar member (symlink/hardlink): {member.name}"
            )
        if member.isdev() or member.ischr() or member.isblk():
            raise RuntimeError(
                f"Unsafe tar member (device file): {member.name}"
            )
        
        # Extract regular files and directories only
        if member.isfile() or member.isdir():
            tar.extract(member, extract_dir)


def safe_extract_zip(zf: zipfile.ZipFile, extract_dir: Path):
    """Safely extract zip archive preventing path traversal.
    
    Args:
        zf: zipfile.ZipFile object
        extract_dir: Destination directory
        
    Raises:
        RuntimeError: If any member attempts path traversal
    """
    extract_dir = extract_dir.resolve()
    
    for name in zf.namelist():
        member_path = (extract_dir / name).resolve()
        
        # Check path traversal
        if not str(member_path).startswith(str(extract_dir)):
            raise RuntimeError(
                f"Path traversal attempt: {name} outside {extract_dir}"
            )
        
        # Extract
        if name.endswith('/'):
            member_path.mkdir(parents=True, exist_ok=True)
        else:
            member_path.parent.mkdir(parents=True, exist_ok=True)
            member_path.write_bytes(zf.read(name))
