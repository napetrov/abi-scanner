"""Unit tests for abicc_backend module and _combined_status helper."""
import sys
import textwrap
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from abi_scanner.abicc_backend import AbiccBackend, AbiccResult, _parse_html_report, has_debug_info
from scripts.compare_all_history import _combined_status


MINIMAL_HTML = textwrap.dedent("""\
    <html><body>
    <table>
    <tr><td>Binary compatibility: 97.5%</td></tr>
    <tr><td>Source compatibility: 95.0%</td></tr>
    <tr><td>Binary problems: 3</td></tr>
    <tr><td>Source problems: 7</td></tr>
    <tr><td>Added Symbols: 12</td></tr>
    <tr><td>Removed Symbols: 5</td></tr>
    </table>
    <a name="Source_Removed"></a>
    <span class="iname">some_removed_function(int)</span>
    <span class="iname">another_symbol</span>
    </body></html>
""")


def _make_abicc(src=100.0, bin=100.0, src_prob=0, bin_prob=0):
    return AbiccResult(
        source_compat=src,
        binary_compat=bin,
        source_problems=src_prob,
        binary_problems=bin_prob,
    )


class TestCombinedStatus:
    def test_no_abicc_returns_abidiff_status(self):
        assert _combined_status(0, None) == "NO_CHANGE"
        assert _combined_status(4, None) == "COMPATIBLE"

    def test_binary_break(self):
        r = _make_abicc(bin=90.0)
        assert _combined_status(4, r) == "BINARY_BREAK"

    def test_source_break(self):
        r = _make_abicc(src=95.0)
        assert _combined_status(4, r) == "SOURCE_BREAK"


class TestParseHtml:
    def test_parse_metrics(self, tmp_path):
        p = tmp_path / "report.html"
        p.write_text(MINIMAL_HTML, encoding="utf-8")
        result = _parse_html_report(p)
        assert result.binary_compat == pytest.approx(97.5)
        assert result.source_compat == pytest.approx(95.0)
        assert result.added_symbols == 12
        assert "another_symbol" in result.removed_symbol_names


class TestHasDebugInfo:
    def test_readelf_finds_debug_info(self, tmp_path):
        lib = tmp_path / "libx.so"
        lib.write_text("x")

        def _which(name):
            return f"/usr/bin/{name}" if name == "readelf" else None

        cp = subprocess.CompletedProcess(["readelf"], 0, stdout="[29] .debug_info PROGBITS", stderr="")
        with patch("shutil.which", side_effect=_which), patch("subprocess.run", return_value=cp):
            assert has_debug_info(lib) is True

    def test_fallback_to_objdump(self, tmp_path):
        lib = tmp_path / "libx.so"
        lib.write_text("x")

        def _which(name):
            if name == "readelf":
                return None
            if name == "objdump":
                return "/usr/bin/objdump"
            return None

        cp = subprocess.CompletedProcess(["objdump"], 0, stdout=" 12 .zdebug_info 00000020", stderr="")
        with patch("shutil.which", side_effect=_which), patch("subprocess.run", return_value=cp):
            assert has_debug_info(lib) is True


class TestAbiccBackendRun:
    def _mk_inputs(self, tmp_path):
        old_lib = tmp_path / "old.so"
        new_lib = tmp_path / "new.so"
        old_lib.write_text("x")
        new_lib.write_text("x")
        old_inc = tmp_path / "old_inc"
        new_inc = tmp_path / "new_inc"
        old_inc.mkdir()
        new_inc.mkdir()
        return old_lib, new_lib, old_inc, new_inc

    def test_uses_dump_mode_when_debug_and_tools_available(self, tmp_path):
        old_lib, new_lib, old_inc, new_inc = self._mk_inputs(tmp_path)
        work = tmp_path / "work"

        def _which(name):
            bins = {
                "abi-compliance-checker", "abi-dumper", "vtable-dumper", "ctags", "readelf"
            }
            return f"/usr/bin/{name}" if name in bins else None

        calls = []

        def _run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0].endswith("readelf"):
                return subprocess.CompletedProcess(cmd, 0, stdout=".debug_info", stderr="")
            if cmd[0].endswith("abi-dumper"):
                dump_path = Path(cmd[cmd.index("-o") + 1])
                dump_path.write_text("dump")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[0].endswith("abi-compliance-checker") and "-strict" in cmd:
                report_path = Path(cmd[cmd.index("-report-path") + 1])
                report_path.write_text(MINIMAL_HTML, encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            raise AssertionError(f"Unexpected command: {cmd}")

        backend = AbiccBackend()
        with patch("shutil.which", side_effect=_which), patch("subprocess.run", side_effect=_run):
            result = backend.run(
                old_version="1.0", old_lib_path=old_lib, old_headers_path=old_inc,
                new_version="1.1", new_lib_path=new_lib, new_headers_path=new_inc,
                library_name="libx", skip_headers=[], work_dir=work,
            )

        assert result.error is None
        assert result.mode == "dump"
        assert result.debug_info_old is True and result.debug_info_new is True
        assert result.dump_mode_attempted is True
        assert any((c[0].endswith("abi-dumper") for c in calls))

    def test_dump_failure_falls_back_to_headers_mode(self, tmp_path):
        old_lib, new_lib, old_inc, new_inc = self._mk_inputs(tmp_path)
        work = tmp_path / "work"

        def _which(name):
            bins = {
                "abi-compliance-checker", "abi-dumper", "vtable-dumper", "ctags", "readelf"
            }
            return f"/usr/bin/{name}" if name in bins else None

        def _run(cmd, **kwargs):
            if cmd[0].endswith("readelf"):
                return subprocess.CompletedProcess(cmd, 0, stdout=".debug_info", stderr="")
            if cmd[0].endswith("abi-dumper"):
                return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="dump fail")
            if cmd[0].endswith("abi-compliance-checker") and "-lib" in cmd:
                report_path = Path(cmd[cmd.index("-report-path") + 1])
                report_path.write_text(MINIMAL_HTML, encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            raise AssertionError(f"Unexpected command: {cmd}")

        backend = AbiccBackend()
        with patch("shutil.which", side_effect=_which), patch("subprocess.run", side_effect=_run):
            result = backend.run(
                old_version="1.0", old_lib_path=old_lib, old_headers_path=old_inc,
                new_version="1.1", new_lib_path=new_lib, new_headers_path=new_inc,
                library_name="libx", skip_headers=[], work_dir=work,
            )

        assert result.error is None
        assert result.mode == "headers"
        assert result.dump_mode_attempted is True
