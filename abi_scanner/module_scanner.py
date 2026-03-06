"""Symbol classification helpers for ABI scan workflows."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Dict, List, Iterable, Tuple


CategoryStats = Dict[str, Dict[str, int]]
CategorySymbols = Dict[str, Dict[str, List[str]]]


def demangle_symbols(symbols: "list[str]") -> "dict[str, str]":
    """Batch demangle C++ symbols using a single c++filt invocation.

    Returns a dict mapping mangled -> demangled. Falls back to identity on error.
    """
    if not symbols:
        return {}
    cppfilt = shutil.which("c++filt")
    if not cppfilt:
        return {s: s for s in symbols}
    try:
        r = subprocess.run(
            [cppfilt],
            input="\n".join(symbols),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            demangled = r.stdout.splitlines()
            return dict(zip(symbols, demangled[:len(symbols)]))
    except Exception:
        pass
    return {s: s for s in symbols}


def demangle_symbol(symbol: str) -> str:
    """Demangle a single C++ symbol using c++filt.

    Returns the original symbol if demangling fails.
    Convenience wrapper around demangle_symbols().
    """
    return demangle_symbols([symbol]).get(symbol, symbol)


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
        # Match ELF-level: "Removed/Added function symbols"
        # Match DWARF-level: "N Removed functions:" / "N Added functions:"
        if "Removed function symbol" in s or "Removed variable symbol" in s \
                or ("Removed function" in s and (s.endswith("functions:") or s.endswith("function:"))) \
                or ("Removed variable" in s and (s.endswith("variables:") or s.endswith("variable:"))):
            current_section = "removed"
        elif "Added function symbol" in s or "Added variable symbol" in s \
                or ("Added function" in s and (s.endswith("functions:") or s.endswith("function:"))) \
                or ("Added variable" in s and (s.endswith("variables:") or s.endswith("variable:"))):
            current_section = "added"
        elif "Changed function" in s or "Changed variable" in s:
            current_section = "changed"
        elif s.endswith("symbols:") and "function symbols" not in s \
                and "variable symbols" not in s:
            current_section = None
        elif (s.startswith("[D]") or s.startswith("[A]") or s.startswith("[C]")) \
                and current_section:
            parts = s.split(maxsplit=1)
            symbol = parts[1] if len(parts) > 1 else ""
            # Strip trailing mangled form e.g. {_ZNxxx}
            symbol = symbol.split("{")[0].strip().strip("'").strip()
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
