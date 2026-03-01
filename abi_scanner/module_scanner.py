"""Symbol classification helpers for ABI scan workflows."""

from __future__ import annotations

import re
import subprocess
from typing import Dict, List, Iterable, Tuple


CategoryStats = Dict[str, Dict[str, int]]
CategorySymbols = Dict[str, Dict[str, List[str]]]


def demangle_symbol(symbol: str) -> str:
    """Demangle a C++ symbol using c++filt.

    Returns the original symbol if demangling fails.
    """
    try:
        result = subprocess.run(
            ["c++filt", symbol], capture_output=True, text=True, timeout=1, check=False
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return symbol


class SymbolClassifier:
    """Classify C++ symbols into public/preview/internal API buckets."""

    def __init__(self) -> None:
        self.internal_patterns = [
            r"::detail::",
            r"::backend::",
            r"::internal::",
            r"::impl::",
            r"^mkl_serv_",
            r"^tbb::",
            r"^daal::.*::internal::",
        ]
        self.preview_patterns = [r"::preview::", r"::experimental::"]
        self._internal_re = [re.compile(p) for p in self.internal_patterns]
        self._preview_re = [re.compile(p) for p in self.preview_patterns]

    def classify(self, symbol: str) -> str:
        demangled = demangle_symbol(symbol) if symbol.startswith("_Z") else symbol
        for p in self._internal_re:
            if p.search(demangled):
                return "internal"
        for p in self._preview_re:
            if p.search(demangled):
                return "preview"
        return "public"


def iter_abidiff_symbols(stdout: str) -> Iterable[Tuple[str, str]]:
    """Yield (section, raw_symbol) tuples from abidiff stdout."""
    current_section = None
    for line in stdout.splitlines():
        s = line.strip()
        if "Removed function symbols" in s:
            current_section = "removed"
        elif "Added function symbols" in s:
            current_section = "added"
        elif s.endswith("symbols:") and "function symbols" not in s:
            current_section = None
        elif (s.startswith("[D]") or s.startswith("[A]")) and current_section:
            parts = s.split(maxsplit=1)
            symbol = parts[1] if len(parts) > 1 else ""
            yield current_section, symbol


def parse_abidiff_symbols(stdout: str, classifier: SymbolClassifier) -> CategoryStats:
    """Parse abidiff output and classify symbol delta counts by category."""
    stats: CategoryStats = {
        "public": {"removed": 0, "added": 0},
        "preview": {"removed": 0, "added": 0},
        "internal": {"removed": 0, "added": 0},
    }
    for section, symbol in iter_abidiff_symbols(stdout):
        cat = classifier.classify(symbol)
        if cat in stats:
            stats[cat][section] += 1
    return stats


def extract_symbol_lists(stdout: str, classifier: SymbolClassifier) -> CategorySymbols:
    """Extract per-category lists of added/removed symbols from abidiff output."""
    result: CategorySymbols = {
        "public": {"removed": [], "added": []},
        "preview": {"removed": [], "added": []},
        "internal": {"removed": [], "added": []},
    }
    for section, symbol in iter_abidiff_symbols(stdout):
        demangled = demangle_symbol(symbol) if symbol.startswith("_Z") else symbol
        cat = classifier.classify(demangled)
        if cat in result:
            result[cat][section].append(demangled)
    return result
