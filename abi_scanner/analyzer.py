"""ABI analysis using libabigail (abidw/abidiff)

This module provides ABI baseline generation and comparison functionality.
"""

import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set


def demangle_symbol(mangled: str) -> str:
    """Demangle C++ symbol using c++filt."""
    try:
        result = subprocess.run(
            ["c++filt", mangled],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return mangled


def extract_namespace(demangled: str) -> str:
    """Extract primary namespace from demangled symbol.
    
    Examples:
        'oneapi::dal::v2::array<int>::operator=' -> 'oneapi::dal'
        'daal::algorithms::covariance::Batch::compute' -> 'daal::algorithms'
        'std::__detail::__variant::foo' -> 'std'
    """
    # Remove template args, function args, return types
    simplified = re.sub(r'<[^>]*>', '', demangled)
    simplified = re.sub(r'\([^)]*\)', '', simplified)
    
    # Extract namespace parts (before last ::)
    parts = simplified.split('::')
    if len(parts) <= 1:
        return "(global)"
    
    # Return first 2 levels (e.g., oneapi::dal, daal::algorithms)
    # Skip detail/internal/backend parts
    ns_parts = []
    for part in parts[:-1]:  # Exclude last part (class/function name)
        if part in ('detail', 'internal', 'backend', 'impl', 'v1', 'v2', 'interface1', 'interface2'):
            break
        ns_parts.append(part)
        if len(ns_parts) >= 2:
            break
    
    return '::'.join(ns_parts) if ns_parts else "(global)"


class ABIVerdict(Enum):
    """ABI compatibility verdict based on abidiff exit code"""
    NO_CHANGE = 0      # Exit 0: No ABI changes
    COMPATIBLE = 4     # Exit 4: Additions only (compatible)
    INCOMPATIBLE = 8   # Exit 8: ABI changes detected
    BREAKING = 12      # Exit 12: Symbols removed/changed (breaking)
    ERROR = -1         # Analysis error


@dataclass
class ABIChange:
    """Single ABI change (added/removed/changed symbol)"""
    kind: str  # "added", "removed", "changed"
    symbol: str
    is_public: bool


@dataclass
class ABIComparisonResult:
    """Result of ABI comparison between two baselines"""
    verdict: ABIVerdict
    exit_code: int
    baseline_old: str
    baseline_new: str
    
    # Summary counters
    functions_removed: int = 0
    functions_changed: int = 0
    functions_added: int = 0
    variables_removed: int = 0
    variables_changed: int = 0
    variables_added: int = 0
    
    # Detailed changes (categorized by public/private)
    public_added: List[str] = field(default_factory=list)
    public_removed: List[str] = field(default_factory=list)
    public_changed: List[str] = field(default_factory=list)
    private_added: List[str] = field(default_factory=list)
    private_removed: List[str] = field(default_factory=list)
    private_changed: List[str] = field(default_factory=list)
    
    # Raw abidiff output
    stdout: str = ""
    stderr: str = ""
    
    def group_by_namespace(self, symbols: List[str]) -> Dict[str, List[str]]:
        """Group symbols by namespace."""
        grouped = defaultdict(list)
        for sym in symbols:
            demangled = demangle_symbol(sym)
            ns = extract_namespace(demangled)
            grouped[ns].append(demangled)
        return dict(grouped)
    
    def format_summary(self, show_rc: bool = False) -> str:
        """Format human-readable summary."""
        lines = []
        
        # Verdict
        verdict_map = {
            ABIVerdict.NO_CHANGE: "✅ NO_CHANGE",
            ABIVerdict.COMPATIBLE: "✅ COMPATIBLE",
            ABIVerdict.INCOMPATIBLE: "⚠️  INCOMPATIBLE",
            ABIVerdict.BREAKING: "❌ BREAKING",
            ABIVerdict.ERROR: "❌ ERROR"
        }
        verdict_str = verdict_map.get(self.verdict, f"?({self.verdict.name})")
        
        if show_rc:
            verdict_str += f" (rc={self.exit_code})"
        
        lines.append(verdict_str)
        
        # Counters
        if self.functions_removed or self.functions_added or self.functions_changed:
            parts = []
            if self.functions_removed:
                parts.append(f"-{self.functions_removed}")
            if self.functions_added:
                parts.append(f"+{self.functions_added}")
            if self.functions_changed:
                parts.append(f"~{self.functions_changed}")
            lines.append(f"Functions: {' '.join(parts)}")
        
        if self.variables_removed or self.variables_added or self.variables_changed:
            parts = []
            if self.variables_removed:
                parts.append(f"-{self.variables_removed}")
            if self.variables_added:
                parts.append(f"+{self.variables_added}")
            if self.variables_changed:
                parts.append(f"~{self.variables_changed}")
            lines.append(f"Variables: {' '.join(parts)}")
        
        return " | ".join(lines)
    
    def format_details(self, max_per_ns: int = 5) -> str:
        """Format detailed symbol changes grouped by namespace."""
        lines = []
        
        if self.public_removed:
            lines.append("\n📉 Removed (public API):")
            grouped = self.group_by_namespace(self.public_removed)
            for ns, syms in sorted(grouped.items()):
                lines.append(f"  {ns}:")
                for sym in syms[:max_per_ns]:
                    lines.append(f"    - {sym}")
                if len(syms) > max_per_ns:
                    lines.append(f"    ... and {len(syms) - max_per_ns} more")
        
        if self.public_added:
            lines.append("\n📈 Added (public API):")
            grouped = self.group_by_namespace(self.public_added)
            for ns, syms in sorted(grouped.items()):
                lines.append(f"  {ns}:")
                for sym in syms[:max_per_ns]:
                    lines.append(f"    + {sym}")
                if len(syms) > max_per_ns:
                    lines.append(f"    ... and {len(syms) - max_per_ns} more")
        
        if self.public_changed:
            lines.append("\n🔄 Changed (public API):")
            grouped = self.group_by_namespace(self.public_changed)
            for ns, syms in sorted(grouped.items()):
                lines.append(f"  {ns}:")
                for sym in syms[:max_per_ns]:
                    lines.append(f"    ~ {sym}")
                if len(syms) > max_per_ns:
                    lines.append(f"    ... and {len(syms) - max_per_ns} more")
        
        return "\n".join(lines) if lines else ""
    
    def to_dict(self) -> dict:
        """Export as JSON-serializable dict"""
        return {
            "comparison": f"{Path(self.baseline_old).stem} → {Path(self.baseline_new).stem}",
            "verdict": self.verdict.name,
            "exit_code": self.exit_code,
            "summary": {
                "functions": {
                    "removed": self.functions_removed,
                    "changed": self.functions_changed,
                    "added": self.functions_added,
                },
                "variables": {
                    "removed": self.variables_removed,
                    "changed": self.variables_changed,
                    "added": self.variables_added,
                }
            },
            "changes": {
                "public": {
                    "added": len(self.public_added),
                    "removed": len(self.public_removed),
                    "changed": len(self.public_changed),
                },
                "private": {
                    "added": len(self.private_added),
                    "removed": len(self.private_removed),
                    "changed": len(self.private_changed),
                }
            },
            "details": {
                "public_added_by_ns": self.group_by_namespace(self.public_added),
                "public_removed_by_ns": self.group_by_namespace(self.public_removed),
                "public_changed_by_ns": self.group_by_namespace(self.public_changed),
            }
        }


class PublicAPIFilter:
    """Filter to classify symbols as public/private API"""
    
    def __init__(self, public_namespaces: Optional[List[str]] = None):
        self.public_namespaces = public_namespaces or []
        
        # Common private patterns
        self.private_patterns = [
            r"::detail::",
            r"::backend::",
            r"::internal::",
            r"::impl::",
            r"^mkl_",
            r"tbb::detail::",
            r"_Z.*internal",
        ]
        self._compiled_patterns = [re.compile(p) for p in self.private_patterns]
        
        # Compile public namespace patterns with boundary matching
        # to avoid false positives like "foo" matching "foobar::..."
        self._public_ns_patterns = [
            re.compile(rf"(?:^|::){re.escape(ns)}(?:$|::)")
            for ns in self.public_namespaces
        ]
    
    def is_public(self, symbol: str) -> bool:
        """Check if symbol belongs to public API"""
        # First check against private patterns (fast reject)
        for pattern in self._compiled_patterns:
            if pattern.search(symbol):
                return False
        
        # If no public namespaces defined, assume public
        if not self._public_ns_patterns:
            return True
        
        # Check if symbol matches any public namespace (boundary-aware)
        for pattern in self._public_ns_patterns:
            if pattern.search(symbol):
                return True
        
        return False
    
    @classmethod
    def from_json(cls, api_file: Path) -> "PublicAPIFilter":
        """Load public API definition from JSON file
        
        Args:
            api_file: Path to public API JSON manifest
            
        Returns:
            PublicAPIFilter instance
            
        Note:
            If file doesn't exist, returns filter with no public namespaces
            (treats all as public except private patterns). This is intentional
            for optional public API filtering, but callers should validate
            file existence if strict filtering is required.
        """
        if not api_file.exists():
            import warnings
            warnings.warn(
                f"Public API manifest not found: {api_file}. "
                f"Defaulting to 'all public' (except private patterns).",
                UserWarning,
                stacklevel=2
            )
            return cls()
        
        with open(api_file) as f:
            data = json.load(f)
        
        public_ns = data.get("namespaces", {}).get("public", [])
        return cls(public_namespaces=public_ns)


class ABIAnalyzer:
    """High-level ABI analysis using libabigail"""
    
    def __init__(self, suppressions: Optional[Path] = None):
        """
        Args:
            suppressions: Path to abidiff suppressions file (optional)
        """
        self.suppressions = suppressions
        self._check_tools()
    
    def _check_tools(self):
        """Verify abidw/abidiff are available"""
        try:
            subprocess.run(["abidw", "--version"], capture_output=True, check=True)
            subprocess.run(["abidiff", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                "libabigail tools (abidw/abidiff) not found. "
                "Install: apt-get install abigail-tools"
            ) from e
    
    def generate_baseline(
        self,
        binary_path: Path,
        output_path: Path,
        headers: Optional[List[Path]] = None
    ) -> None:
        """Generate ABI baseline using abidw
        
        Args:
            binary_path: Path to shared library (.so)
            output_path: Where to save ABI XML baseline
            headers: Optional list of public header files
        
        Raises:
            subprocess.CalledProcessError: If abidw fails
        """
        cmd = ["abidw"]
        
        if headers:
            for header in headers:
                cmd.extend(["--headers-dir", str(header.parent)])
        
        cmd.extend([
            "--out-file", str(output_path),
            str(binary_path)
        ])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                output=result.stdout,
                stderr=result.stderr
            )
    
    def compare(
        self,
        baseline_old: Path,
        baseline_new: Path,
        api_filter_old: Optional[PublicAPIFilter] = None,
        api_filter_new: Optional[PublicAPIFilter] = None
    ) -> ABIComparisonResult:
        """Compare two ABI baselines using abidiff
        
        Args:
            baseline_old: Path to old ABI baseline (XML)
            baseline_new: Path to new ABI baseline (XML)
            api_filter_old: Public API filter for old version
            api_filter_new: Public API filter for new version
        
        Returns:
            ABIComparisonResult with verdict and detailed changes
        """
        # Run abidiff
        cmd = ["abidiff"]
        
        if self.suppressions and self.suppressions.exists():
            cmd.extend(["--suppressions", str(self.suppressions)])
        
        cmd.extend([str(baseline_old), str(baseline_new)])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse output
        comparison = ABIComparisonResult(
            verdict=self._categorize_exit_code(result.returncode),
            exit_code=result.returncode,
            baseline_old=str(baseline_old),
            baseline_new=str(baseline_new),
            stdout=result.stdout,
            stderr=result.stderr
        )
        
        # Parse summary
        self._parse_summary(result.stdout, comparison)
        
        # Parse detailed changes
        self._parse_changes(
            result.stdout,
            comparison,
            api_filter_old or PublicAPIFilter(),
            api_filter_new or PublicAPIFilter()
        )
        
        return comparison
    
    def _categorize_exit_code(self, exit_code: int) -> ABIVerdict:
        """Map abidiff exit code to verdict"""
        mapping = {
            0: ABIVerdict.NO_CHANGE,
            4: ABIVerdict.COMPATIBLE,
            8: ABIVerdict.INCOMPATIBLE,
            12: ABIVerdict.BREAKING,
        }
        return mapping.get(exit_code, ABIVerdict.ERROR)
    
    def _parse_summary(self, output: str, result: ABIComparisonResult):
        """Parse summary counters from abidiff output"""
        # Functions changes summary: X Removed, Y Changed, Z Added
        func_match = re.search(
            r"Functions changes summary: (\d+) Removed, (\d+) Changed, (\d+) Added",
            output
        )
        if func_match:
            result.functions_removed = int(func_match.group(1))
            result.functions_changed = int(func_match.group(2))
            result.functions_added = int(func_match.group(3))
        
        # Also parse "X Added/Removed function symbols not referenced by debug info"
        func_no_debug_added = re.search(
            r"(\d+) Added function symbols not referenced by debug info",
            output
        )
        if func_no_debug_added:
            result.functions_added += int(func_no_debug_added.group(1))
        
        func_no_debug_removed = re.search(
            r"(\d+) Removed function symbols not referenced by debug info",
            output
        )
        if func_no_debug_removed:
            result.functions_removed += int(func_no_debug_removed.group(1))
        
        # Variables changes summary: X Removed, Y Changed, Z Added
        var_match = re.search(
            r"Variables changes summary: (\d+) Removed, (\d+) Changed, (\d+) Added",
            output
        )
        if var_match:
            result.variables_removed = int(var_match.group(1))
            result.variables_changed = int(var_match.group(2))
            result.variables_added = int(var_match.group(3))
        
        # Also parse "X Added/Removed variable symbols not referenced by debug info"
        var_no_debug_added = re.search(
            r"(\d+) Added variable symbols? not referenced by debug info",
            output
        )
        if var_no_debug_added:
            result.variables_added += int(var_no_debug_added.group(1))
        
        var_no_debug_removed = re.search(
            r"(\d+) Removed variable symbols? not referenced by debug info",
            output
        )
        if var_no_debug_removed:
            result.variables_removed += int(var_no_debug_removed.group(1))
    
    def _parse_changes(
        self,
        output: str,
        result: ABIComparisonResult,
        api_filter_old: PublicAPIFilter,
        api_filter_new: PublicAPIFilter
    ):
        """Parse detailed symbol changes from abidiff output"""
        lines = output.split('\n')
        current_section = None
        
        for line in lines:
            # Detect section headers (including "not referenced by debug info" variants)
            if ("Removed function symbols" in line or "Removed variable symbols" in line):
                current_section = "removed"
                continue
            elif ("Added function symbols" in line or "Added variable symbols" in line):
                current_section = "added"
                continue
            elif ("Changed function symbols" in line or "Changed variable symbols" in line):
                current_section = "changed"
                continue
            
            # Parse symbols
            stripped = line.strip()
            
            if current_section == "removed" and stripped.startswith('[D]'):
                symbol = stripped[4:].strip()
                if api_filter_old.is_public(symbol):
                    result.public_removed.append(symbol)
                else:
                    result.private_removed.append(symbol)
            
            elif current_section == "added" and stripped.startswith('[A]'):
                symbol = stripped[4:].strip()
                if api_filter_new.is_public(symbol):
                    result.public_added.append(symbol)
                else:
                    result.private_added.append(symbol)
            
            elif current_section == "changed" and stripped.startswith('[C]'):
                symbol = stripped[4:].strip()
                # Use new version's filter for changed symbols
                if api_filter_new.is_public(symbol):
                    result.public_changed.append(symbol)
                else:
                    result.private_changed.append(symbol)
