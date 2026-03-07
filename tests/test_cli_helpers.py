"""Tests for _pick_library helper."""
import warnings
from pathlib import Path
from abi_scanner.cli import _pick_library


def test_pick_library_empty():
    assert _pick_library({}, None) is None


def test_pick_library_single():
    libs = {"libfoo.so": Path("/lib/libfoo.so")}
    name, path = _pick_library(libs, None)
    assert name == "libfoo.so"
    assert path == Path("/lib/libfoo.so")


def test_pick_library_by_name():
    libs = {"libfoo.so": Path("/lib/libfoo.so"), "libbar.so": Path("/lib/libbar.so")}
    name, _ = _pick_library(libs, "libbar.so")
    assert name == "libbar.so"


def test_pick_library_multi_warns():
    libs = {
        "libmkl_rt.so": Path("/lib/libmkl_rt.so"),
        "libmkl_core.so": Path("/lib/libmkl_core.so"),
    }
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _pick_library(libs, None)
        assert len(w) == 1
        assert "Multiple libraries" in str(w[0].message)
    assert result is not None
    # Should pick alphabetically first
    assert result[0] == "libmkl_core.so"
