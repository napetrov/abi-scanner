"""Tests for ABI analyzer module."""


from abi_scanner.analyzer import ABIAnalyzer, ABIVerdict, PublicAPIFilter, ABIComparisonResult


def test_public_api_filter_private_patterns_win():
    filt = PublicAPIFilter(public_namespaces=["oneapi::dal"])

    assert filt.is_public("oneapi::dal::model::fit") is True
    assert filt.is_public("oneapi::dal::detail::impl") is False
    assert filt.is_public("tbb::detail::r1::task") is False


def test_public_api_filter_without_namespaces_defaults_public():
    filt = PublicAPIFilter()
    assert filt.is_public("any::symbol") is True
    assert filt.is_public("mkl_internal_symbol") is False


def test_public_api_filter_from_missing_json(tmp_path):
    filt = PublicAPIFilter.from_json(tmp_path / "missing.json")
    assert filt.is_public("foo::bar") is True


def test_verdict_mapping_without_tool_init():
    analyzer = ABIAnalyzer.__new__(ABIAnalyzer)

    assert analyzer._categorize_exit_code(0) == ABIVerdict.NO_CHANGE
    assert analyzer._categorize_exit_code(4) == ABIVerdict.COMPATIBLE
    assert analyzer._categorize_exit_code(8) == ABIVerdict.INCOMPATIBLE
    assert analyzer._categorize_exit_code(12) == ABIVerdict.BREAKING
    assert analyzer._categorize_exit_code(42) == ABIVerdict.ERROR


def test_parse_summary():
    analyzer = ABIAnalyzer.__new__(ABIAnalyzer)
    result = ABIComparisonResult(
        verdict=ABIVerdict.NO_CHANGE,
        exit_code=0,
        baseline_old="old.xml",
        baseline_new="new.xml",
    )

    output = (
        "Functions changes summary: 1 Removed, 2 Changed, 3 Added\n"
        "Variables changes summary: 4 Removed, 5 Changed, 6 Added\n"
    )
    analyzer._parse_summary(output, result)

    assert result.functions_removed == 1
    assert result.functions_changed == 2
    assert result.functions_added == 3
    assert result.variables_removed == 4
    assert result.variables_changed == 5
    assert result.variables_added == 6
