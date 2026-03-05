"""Unit tests for abicc_backend module and _combined_status helper."""
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from abi_scanner.abicc_backend import AbiccBackend, AbiccResult, _parse_html_report
from scripts.compare_all_history import _combined_status


# ---------------------------------------------------------------------------
# _combined_status tests
# ---------------------------------------------------------------------------

def _make_abicc(src=100.0, bin=100.0, src_prob=0, bin_prob=0):
    return AbiccResult(
        source_compat=src, binary_compat=bin,
        source_problems=src_prob, binary_problems=bin_prob,
    )


class TestCombinedStatus:
    def test_no_abicc_returns_abidiff_status(self):
        assert _combined_status(0, None) == "NO_CHANGE"
        assert _combined_status(4, None) == "COMPATIBLE"
        assert _combined_status(12, None) == "BREAKING"

    def test_abicc_error_returns_abidiff_status(self):
        r = AbiccResult(error="some error")
        assert _combined_status(4, r) == "COMPATIBLE"
        assert _combined_status(12, r) == "BREAKING"

    def test_source_break_when_compatible_abidiff(self):
        # abidiff says COMPATIBLE (4) but ABICC finds source issue → SOURCE_BREAK
        r = _make_abicc(src=95.0)
        assert _combined_status(4, r) == "SOURCE_BREAK"

    def test_source_break_when_binary_compat_low(self):
        # binary-only break (source still 100%) -> BINARY_BREAK
        r = _make_abicc(bin=90.0)
        assert _combined_status(4, r) == "BINARY_BREAK"

    def test_binary_break_flag_via_problems(self):
        # binary problems only (no source break) -> BINARY_BREAK
        r = _make_abicc(bin_prob=3)
        assert _combined_status(4, r) == "BINARY_BREAK"

    def test_breaking_plus_abicc_source_break_stays_breaking(self):
        r = _make_abicc(src=80.0)
        assert _combined_status(12, r) == "BREAKING"

    def test_elf_internal_when_abidiff_breaking_abicc_clean(self, caplog):
        # abidiff=BREAKING (12) but ABICC says 100% clean → ELF_INTERNAL + warning
        import logging
        r = _make_abicc()
        with caplog.at_level(logging.WARNING):
            result = _combined_status(12, r, old_ver="1.0", new_ver="1.1")
        assert result == "ELF_INTERNAL"
        assert "ELF_INTERNAL" in caplog.text
        assert "Manual review recommended" in caplog.text

    def test_no_change_when_both_clean(self):
        r = _make_abicc()
        assert _combined_status(0, r) == "NO_CHANGE"

    def test_compatible_when_both_clean(self):
        r = _make_abicc()
        assert _combined_status(4, r) == "COMPATIBLE"


    def test_binary_break_vs_source_break(self):
        # Both source AND binary break -> SOURCE_BREAK (source is primary)
        r = _make_abicc(src=90.0, bin=80.0)
        assert _combined_status(4, r) == "SOURCE_BREAK"

    def test_binary_only_break_returns_binary_break(self):
        # Only binary break (source 100%) -> BINARY_BREAK
        r = _make_abicc(src=100.0, bin=85.0)
        assert _combined_status(4, r) == "BINARY_BREAK"

# ---------------------------------------------------------------------------
# _parse_html_report tests
# ---------------------------------------------------------------------------

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


class TestParseHtmlReport:
    def test_missing_file(self, tmp_path):
        result = _parse_html_report(tmp_path / "nonexistent.html")
        assert result.error is not None
        assert "not found" in result.error

    def test_basic_metrics(self, tmp_path):
        p = tmp_path / "report.html"
        p.write_text(MINIMAL_HTML, encoding="utf-8")
        result = _parse_html_report(p)
        assert result.error is None
        assert result.binary_compat == pytest.approx(97.5)
        assert result.source_compat == pytest.approx(95.0)
        assert result.binary_problems == 3
        assert result.source_problems == 7
        assert result.added_symbols == 12
        assert result.removed_symbols == 5

    def test_removed_symbols_extracted_via_iname(self, tmp_path):
        p = tmp_path / "report.html"
        p.write_text(MINIMAL_HTML, encoding="utf-8")
        result = _parse_html_report(p)
        assert "some_removed_function(int)" in result.removed_symbol_names
        assert "another_symbol" in result.removed_symbol_names

    def test_defaults_when_no_matches(self, tmp_path):
        p = tmp_path / "empty.html"
        p.write_text("<html><body>nothing useful here</body></html>", encoding="utf-8")
        result = _parse_html_report(p)
        assert result.error is None
        assert result.binary_compat == 100.0
        assert result.source_compat == 100.0
        assert result.removed_symbol_names == []



# ---------------------------------------------------------------------------
# _write_xml_descriptor tests
# ---------------------------------------------------------------------------

def test_xml_descriptor_has_root_element(tmp_path):
    from abi_scanner.abicc_backend import _write_xml_descriptor
    out = tmp_path / "desc.xml"
    _write_xml_descriptor(out, "1.0", Path("/lib/libfoo.so"), Path("/include"), ["sycl.h"])
    content = out.read_text()
    assert content.startswith("<descriptor>")
    assert content.strip().endswith("</descriptor>")
    assert "<version>1.0</version>" in content
    assert "<skip_headers>" in content
    assert "sycl.h" in content


def test_xml_descriptor_escapes_skip_headers(tmp_path):
    from abi_scanner.abicc_backend import _write_xml_descriptor
    out = tmp_path / "desc.xml"
    _write_xml_descriptor(out, "1.0", Path("/lib/libfoo.so"), Path("/include"), ["a&b.h", "<c>.h"])
    content = out.read_text()
    assert "&amp;" in content
    assert "&lt;" in content
    assert "<descriptor>" in content

# ---------------------------------------------------------------------------
# AbiccBackend.run() — tool not in PATH
# ---------------------------------------------------------------------------

class TestAbiccBackendRun:
    def test_missing_binary_returns_error(self, tmp_path):
        backend = AbiccBackend()
        with patch("shutil.which", return_value=None):
            result = backend.run(
                old_version="1.0", old_lib_path=tmp_path / "old.so",
                old_headers_path=tmp_path / "old_inc",
                new_version="1.1", new_lib_path=tmp_path / "new.so",
                new_headers_path=tmp_path / "new_inc",
                library_name="testlib",
                skip_headers=[],
                work_dir=tmp_path / "work",
            )
        assert result.error is not None
        assert "not found in PATH" in result.error

    def test_cached_report_returned_without_running(self, tmp_path):
        """If report already exists, run() returns cached parse without invoking abicc."""
        work = tmp_path / "work"
        work.mkdir()
        report = work / "report_1.0_vs_1.1.html"
        report.write_text(MINIMAL_HTML, encoding="utf-8")

        backend = AbiccBackend()
        with patch("shutil.which", return_value="/usr/bin/abi-compliance-checker"):
            with patch("subprocess.run") as mock_run:
                result = backend.run(
                    old_version="1.0", old_lib_path=tmp_path / "old.so",
                    old_headers_path=tmp_path / "old_inc",
                    new_version="1.1", new_lib_path=tmp_path / "new.so",
                    new_headers_path=tmp_path / "new_inc",
                    library_name="testlib",
                    skip_headers=[],
                    work_dir=work,
                )
                mock_run.assert_not_called()
        assert result.error is None
        assert result.binary_compat == pytest.approx(97.5)

    def test_missing_headers_path_returns_error(self, tmp_path):
        work = tmp_path / "work"
        old_lib = tmp_path / "old.so"
        old_lib.touch()
        new_lib = tmp_path / "new.so"
        new_lib.touch()

        backend = AbiccBackend()
        with patch("shutil.which", return_value="/usr/bin/abi-compliance-checker"):
            result = backend.run(
                old_version="1.0", old_lib_path=old_lib,
                old_headers_path=tmp_path / "nonexistent_inc",
                new_version="1.1", new_lib_path=new_lib,
                new_headers_path=tmp_path / "new_inc",
                library_name="testlib",
                skip_headers=[],
                work_dir=work,
            )
        assert result.error is not None
        assert "does not exist" in result.error
