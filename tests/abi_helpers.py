"""Shared helper functions for ABI integration tests."""
import subprocess
from pathlib import Path

import pytest


def examples_dir() -> Path:
    """Return the path to the examples/ catalog directory."""
    return Path(__file__).parent.parent / "examples"


def _compile(compiler, src_path, out_path, extra_flags=None):
    cmd = [compiler, "-shared", "-fPIC", "-g", str(src_path), "-o", str(out_path)]
    if extra_flags:
        cmd.extend(extra_flags)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{compiler} failed:\n{result.stderr}")
    return out_path


def compile_so(src_path, out_path, extra_flags=None):
    """Compile a C source file to a shared library using gcc."""
    return _compile("gcc", src_path, out_path, extra_flags)


def compile_so_cpp(src_path, out_path, extra_flags=None):
    """Compile a C++ source file to a shared library using g++."""
    return _compile("g++", src_path, out_path, extra_flags)


def _require_tool(name):
    if subprocess.run(["which", name], capture_output=True).returncode != 0:
        pytest.skip(f"{name} not found in PATH")


def make_abi_baseline(so_path, xml_out):
    """Generate an ABI baseline XML with abidw."""
    _require_tool("abidw")
    result = subprocess.run(
        ["abidw", "--out-file", str(xml_out), str(so_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"abidw failed:\n{result.stderr}")
    return xml_out


def compare_abi(old_xml, new_xml):
    """Run abidiff and return (exit_code, stdout)."""
    _require_tool("abidiff")
    result = subprocess.run(
        ["abidiff", str(old_xml), str(new_xml)],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout
