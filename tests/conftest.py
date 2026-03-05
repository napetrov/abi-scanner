"""Shared fixtures and helpers for ABI integration tests."""
import subprocess
import pytest


def compile_so(src_path, out_path, extra_flags=None):
    """Compile a .c file to a shared library with gcc -shared -fPIC."""
    cmd = ["gcc", "-shared", "-fPIC", "-g", str(src_path), "-o", str(out_path)]
    if extra_flags:
        cmd.extend(extra_flags)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gcc failed: {result.stderr}")
    return out_path


def make_abi_baseline(so_path, xml_out):
    """Generate ABI baseline XML using abidw."""
    abidw = subprocess.run(["which", "abidw"], capture_output=True, text=True)
    if abidw.returncode != 0:
        pytest.skip("abidw not found")
    result = subprocess.run(
        ["abidw", "--out-file", str(xml_out), str(so_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"abidw failed: {result.stderr}")
    return xml_out


def compare_abi(old_xml, new_xml):
    """Compare two ABI baselines using abidiff. Returns (exit_code, stdout)."""
    abidiff = subprocess.run(["which", "abidiff"], capture_output=True, text=True)
    if abidiff.returncode != 0:
        pytest.skip("abidiff not found")
    result = subprocess.run(
        ["abidiff", str(old_xml), str(new_xml)],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout
