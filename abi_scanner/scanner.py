"""High-level ABI scanner façade used by CLI and scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from .analyzer import ABIAnalyzer
from .module_scanner import SymbolClassifier, parse_abidiff_symbols


class ABIScanner:
    """Orchestrates baseline generation + ABI comparison for a single library pair."""

    def __init__(self, suppressions: Optional[Path] = None) -> None:
        self.analyzer = ABIAnalyzer(suppressions=suppressions)
        self.classifier = SymbolClassifier()

    def compare_baselines(self, old_abi: Path, new_abi: Path) -> Tuple[int, dict, str]:
        """Compare two baseline files and return (exit_code, categorized_stats, stdout)."""
        result = self.analyzer.compare(old_abi, new_abi)
        stats = parse_abidiff_symbols(result.stdout, self.classifier)
        return result.exit_code, stats, result.stdout
