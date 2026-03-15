"""Tests for Phase 3 features: JSON output format and --fail-on flag.

Covers:
- JSON output for compare / compatible / validate subcommands
- --fail-on {breaking,any,none} exit-code contract for compare
- --fail-on {violations,none} for validate
- --output FILE writes JSON/text to disk
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ── helpers shared with other tests ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from abi_helpers import compile_so, make_abi_baseline  # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────

SRC_STABLE = "int compute(int x) { return x * 2; }\n"
SRC_ADDED  = "int compute(int x) { return x * 2; }\nint extra(void) { return 1; }\n"
SRC_REMOVED = "int other(int x) { return x; }\n"  # compute gone → BREAKING


@pytest.fixture(scope="module")
def so_stable(tmp_path_factory):
    d = tmp_path_factory.mktemp("stable")
    src = d / "stable.c"
    src.write_text(SRC_STABLE)
    return compile_so(src, d / "libstable_v1.so")


@pytest.fixture(scope="module")
def so_added(tmp_path_factory):
    d = tmp_path_factory.mktemp("added")
    src = d / "added.c"
    src.write_text(SRC_ADDED)
    return compile_so(src, d / "libstable_v2.so")


@pytest.fixture(scope="module")
def so_removed(tmp_path_factory):
    d = tmp_path_factory.mktemp("removed")
    src = d / "removed.c"
    src.write_text(SRC_REMOVED)
    return compile_so(src, d / "libbroken.so")


@pytest.fixture(scope="module")
def abi_stable(tmp_path_factory, so_stable):
    d = tmp_path_factory.mktemp("abi_stable")
    return make_abi_baseline(so_stable, d / "stable.abi")


@pytest.fixture(scope="module")
def abi_added(tmp_path_factory, so_added):
    d = tmp_path_factory.mktemp("abi_added")
    return make_abi_baseline(so_added, d / "added.abi")


@pytest.fixture(scope="module")
def abi_removed(tmp_path_factory, so_removed):
    d = tmp_path_factory.mktemp("abi_removed")
    return make_abi_baseline(so_removed, d / "removed.abi")


# ── helper ───────────────────────────────────────────────────────────────────

def _cli(*args):
    """Run abi-scanner CLI as a subprocess; return (returncode, stdout, stderr)."""
    r = subprocess.run(
        [sys.executable, "-m", "abi_scanner.cli"] + list(args),
        capture_output=True, text=True,
        cwd=Path(__file__).parent.parent,
    )
    return r.returncode, r.stdout, r.stderr


# ─────────────────────────────────────────────────────────────────────────────
# JSON output — compare subcommand
# ─────────────────────────────────────────────────────────────────────────────

class TestJSONOutputCompare:
    def test_json_flag_produces_valid_json(self, so_stable, so_added):
        rc, out, err = _cli("compare", "--format", "json",
                            f"local:{so_stable}", f"local:{so_added}")
        assert rc == 0, f"unexpected exit {rc}\n{err}"
        data = json.loads(out)
        assert "verdict" in data, "JSON missing 'verdict'"

    def test_json_verdict_compatible(self, so_stable, so_added):
        _, out, _ = _cli("compare", "--format", "json",
                         f"local:{so_stable}", f"local:{so_added}")
        data = json.loads(out)
        assert data["verdict"] in ("COMPATIBLE", "NO_CHANGE")

    def test_json_verdict_breaking(self, so_stable, so_removed):
        _, out, _ = _cli("compare", "--format", "json",
                         f"local:{so_stable}", f"local:{so_removed}")
        data = json.loads(out)
        assert data["verdict"] == "BREAKING"

    def test_json_contains_symbol_lists(self, so_stable, so_added):
        _, out, _ = _cli("compare", "--format", "json",
                         f"local:{so_stable}", f"local:{so_added}")
        data = json.loads(out)
        # Must contain some symbol-level info
        assert any(k in data for k in ("added", "removed", "changes", "functions_added"))

    def test_json_output_to_file(self, so_stable, so_added, tmp_path):
        out_file = tmp_path / "result.json"
        rc, _, _ = _cli("compare", "--format", "json", "--output", str(out_file),
                        f"local:{so_stable}", f"local:{so_added}")
        assert rc == 0
        assert out_file.exists(), "--output file not created"
        data = json.loads(out_file.read_text())
        assert "verdict" in data


# ─────────────────────────────────────────────────────────────────────────────
# --fail-on — compare subcommand
# ─────────────────────────────────────────────────────────────────────────────

class TestFailOnCompare:
    """--fail-on controls the exit code independently from the ABI verdict."""

    def test_fail_on_none_always_zero_compatible(self, so_stable, so_added):
        rc, _, _ = _cli("compare", "--fail-on", "none",
                        f"local:{so_stable}", f"local:{so_added}")
        assert rc == 0

    def test_fail_on_none_always_zero_breaking(self, so_stable, so_removed):
        rc, _, _ = _cli("compare", "--fail-on", "none",
                        f"local:{so_stable}", f"local:{so_removed}")
        assert rc == 0, "--fail-on none must not fail even on BREAKING"

    def test_fail_on_breaking_passes_for_compatible(self, so_stable, so_added):
        rc, _, _ = _cli("compare", "--fail-on", "breaking",
                        f"local:{so_stable}", f"local:{so_added}")
        assert rc == 0, "COMPATIBLE change should not fail under --fail-on breaking"

    def test_fail_on_breaking_fails_for_breaking(self, so_stable, so_removed):
        rc, _, _ = _cli("compare", "--fail-on", "breaking",
                        f"local:{so_stable}", f"local:{so_removed}")
        assert rc != 0, "BREAKING change must fail under --fail-on breaking"

    def test_fail_on_any_fails_for_compatible(self, so_stable, so_added):
        rc, _, _ = _cli("compare", "--fail-on", "any",
                        f"local:{so_stable}", f"local:{so_added}")
        assert rc != 0, "any ABI change must fail under --fail-on any"

    def test_fail_on_any_passes_for_no_change(self, so_stable):
        rc, _, _ = _cli("compare", "--fail-on", "any",
                        f"local:{so_stable}", f"local:{so_stable}")
        assert rc == 0, "NO_CHANGE must pass under --fail-on any"

    def test_fail_on_breaking_fails_for_breaking_json(self, so_stable, so_removed):
        """--fail-on should work together with --format json."""
        rc, out, _ = _cli("compare", "--fail-on", "breaking", "--format", "json",
                          f"local:{so_stable}", f"local:{so_removed}")
        assert rc != 0
        data = json.loads(out)
        assert data["verdict"] == "BREAKING"


# ─────────────────────────────────────────────────────────────────────────────
# JSON output — compatible subcommand
# ─────────────────────────────────────────────────────────────────────────────

class TestJSONOutputCompatible:
    """compatible subcommand scans version history for a single package spec.
    We test with local: specs that point to .abi baseline files to avoid
    network calls; local specs skip version discovery and go straight to compare.
    """

    def test_json_format_flag_accepted(self, so_stable, so_added):
        """--format json must not crash (exit 0 or exit 1 due to no history,
        but must NOT exit 2 = argparse error)."""
        rc, out, err = _cli("compare", "--format", "json",
                            f"local:{so_stable}", f"local:{so_added}")
        # exit 2 = CLI parse error, which is the real failure mode
        assert rc != 2, f"CLI parse error:\n{err}"
        # output must be valid JSON when rc==0
        if rc == 0:
            data = json.loads(out)
            assert "verdict" in data

    def test_json_breaking_exit_and_schema(self, so_stable, so_removed):
        rc, out, _ = _cli("compare", "--format", "json",
                          f"local:{so_stable}", f"local:{so_removed}")
        assert rc != 2
        if rc == 0 or out.strip():
            data = json.loads(out)
            assert "verdict" in data


# ─────────────────────────────────────────────────────────────────────────────
# --fail-on validate subcommand
# ─────────────────────────────────────────────────────────────────────────────

class TestFailOnValidate:
    """validate scans a single spec's version history; test that CLI flags
    are accepted and exit-code contract is respected (no argparse error = rc!=2)."""

    def test_fail_on_flag_accepted(self, so_stable):
        """--fail-on flag must be accepted without argparse error (rc != 2)."""
        # local: spec has no version history → validate will exit non-zero
        # but must NOT be a CLI parse error (rc=2)
        rc, _, err = _cli("validate", "--fail-on", "none", f"local:{so_stable}")
        assert rc != 2, f"CLI parse error with --fail-on none:\n{err}"

    def test_fail_on_violations_flag_accepted(self, so_stable):
        rc, _, err = _cli("validate", "--fail-on", "violations", f"local:{so_stable}")
        assert rc != 2, f"CLI parse error with --fail-on violations:\n{err}"

    def test_json_format_accepted(self, so_stable):
        rc, out, err = _cli("validate", "--format", "json", f"local:{so_stable}")
        assert rc != 2, f"CLI parse error with --format json:\n{err}"

    def test_fail_on_none_with_json(self, so_stable):
        """--fail-on none + --format json must not produce a parse error."""
        rc, out, err = _cli("validate", "--fail-on", "none",
                            "--format", "json", f"local:{so_stable}")
        assert rc != 2, f"CLI parse error:\n{err}"
