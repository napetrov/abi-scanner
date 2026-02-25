#!/usr/bin/env python3
"""Compare ABI across all package versions with symbol classification.

This script automates ABI compatibility analysis by:
- Downloading runtime and development packages from conda
- Generating ABI baselines using libabigail (abidw)
- Comparing baselines and classifying symbol changes
- Demangling C++ symbols for accurate classification
- Reporting public, preview, and internal API changes separately
"""
import argparse
import os
import re
import subprocess
import tempfile
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional, Tuple, Dict, List


def demangle_symbol(symbol: str) -> str:
    """Demangle a C++ symbol using c++filt.

    Args:
        symbol: Mangled symbol name

    Returns:
        Demangled symbol name, or original if demangling fails
    """
    try:
        result = subprocess.run(
            ['c++filt', symbol], capture_output=True, text=True, timeout=1, check=False
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return symbol


def extract_namespace(demangled: str) -> str:
    """Extract primary namespace from demangled symbol."""
    simplified = re.sub(r'<[^>]*>', '', demangled)
    simplified = re.sub(r'\([^)]*\)', '', simplified)
    parts = simplified.split('::')
    if len(parts) <= 1:
        return "(global)"
    ns_parts = []
    for part in parts[:-1]:
        if part in ('detail', 'internal', 'backend', 'impl', 'v1', 'v2', 'interface1', 'interface2'):
            break
        ns_parts.append(part)
        if len(ns_parts) >= 2:
            break
    return '::'.join(ns_parts) if ns_parts else "(global)"


class SymbolClassifier:
    """Classify C++ symbols into public, preview, or internal API categories.

    Uses regex patterns on demangled names to identify:
    - Internal: implementation details (::detail::, ::backend::, mkl_serv_, etc.)
    - Preview: unstable/experimental APIs (::preview::, ::experimental::)
    - Public: stable public APIs (everything else)
    """

    def __init__(self):
        """Initialize symbol classifier with predefined patterns."""
        self.internal_patterns = [
            r"::detail::", r"::backend::", r"::internal::", r"::impl::",
            r"^mkl_serv_", r"^tbb::", r"^daal::.*::internal::",
        ]
        self.preview_patterns = [r"::preview::", r"::experimental::"]
        self._internal_re = [re.compile(p) for p in self.internal_patterns]
        self._preview_re  = [re.compile(p) for p in self.preview_patterns]

    def classify(self, symbol: str) -> str:
        """Classify a symbol into 'internal', 'preview', or 'public'.

        Args:
            symbol: Mangled or demangled C++ symbol name

        Returns:
            Category string: 'internal', 'preview', or 'public'
        """
        demangled = demangle_symbol(symbol) if symbol.startswith('_Z') else symbol
        for p in self._internal_re:
            if p.search(demangled):
                return "internal"
        for p in self._preview_re:
            if p.search(demangled):
                return "preview"
        return "public"


def get_package_versions(channel, package):
    """Get all available versions for a package from conda channel.

    Args:
        channel: Conda channel name (e.g., 'conda-forge')
        package: Package name (e.g., 'dal')

    Returns:
        List of version strings sorted by packaging.version.Version
    """
    result = subprocess.run(
        ["micromamba", "search", "-c", channel, package, "--json"],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
    import json
    data = json.loads(result.stdout)
    versions = list(set(pkg["version"] for pkg in data.get("result", {}).get("pkgs", [])))
    from packaging.version import Version
    try:
        return sorted(versions, key=lambda v: Version(v))
    except Exception:
        return sorted(versions)


def download_packages(channel: str, package: str, version: str, env_path: Path,
                      devel_package: Optional[str] = None, verbose: bool = False) -> bool:
    """Download runtime and optional development packages into environment.

    Args:
        channel: Conda channel name
        package: Runtime package name
        version: Package version
        env_path: Path to target environment
        devel_package: Optional development package name (e.g., 'dal-devel')
        verbose: Enable verbose output

    Returns:
        True if successful, False otherwise
    """
    packages = [f"{package}={version}"]
    if devel_package:
        packages.append(f"{devel_package}={version}")
    if verbose:
        print(f"  Downloading: {', '.join(packages)}")
    result = subprocess.run(
        ["micromamba", "create", "-y", "-r", str(env_path.parent / "root"),
         "-p", str(env_path), "-c", channel] + packages,
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        if verbose:
            print(f"  Failed: {result.stderr[-300:]}")
        return False
    return True


def find_library(env_path: Path, package: str, verbose: bool = False) -> Optional[Path]:
    """Find shared library (.so) in conda environment.

    Args:
        env_path: Path to conda environment
        package: Package name to locate library for
        verbose: Enable verbose output

    Returns:
        Path to library if found, None otherwise
    """
    lib_patterns = [f"lib{package}.so*", "libonedal.so*"]
    for pattern in lib_patterns:
        for m in env_path.glob(f"**/{pattern}"):
            if m.suffix == ".so" or m.name.count(".so") == 1:
                if verbose:
                    print(f"  Found: {m}")
                return m
    for pattern in lib_patterns:
        matches = list(env_path.glob(f"**/{pattern}"))
        if matches:
            if verbose:
                print(f"  Found (fallback): {matches[0]}")
            return matches[0]
    return None


def generate_abi_baseline(lib_path: Path, output_path: Path,
                          headers_dir: Optional[Path] = None,
                          suppressions: Optional[Path] = None,
                          verbose: bool = False) -> bool:
    """Generate ABI baseline using abidw.

    Args:
        lib_path: Path to shared library
        output_path: Path to output .abi file
        headers_dir: Optional path to public headers directory
        suppressions: Optional path to suppressions file
        verbose: Enable verbose output

    Returns:
        True if successful, False otherwise
    """
    cmd = ["abidw", "--out-file", str(output_path)]
    if headers_dir and headers_dir.exists():
        cmd.extend(["--headers-dir", str(headers_dir)])
        if verbose:
            print(f"  Using headers: {headers_dir}")
    if suppressions and suppressions.exists():
        cmd.extend(["--suppressions", str(suppressions)])
    cmd.append(str(lib_path))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        if verbose:
            print(f"  abidw failed: {result.stderr[-300:]}")
        return False
    return True


def _iter_abidiff_symbols(stdout: str):
    """Yield (section, raw_symbol) from abidiff stdout."""
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


def parse_abidiff_symbols(stdout: str, classifier: SymbolClassifier) -> Dict[str, Dict[str, int]]:
    """Parse abidiff output and classify symbols by category.

    Args:
        stdout: abidiff stdout output
        classifier: SymbolClassifier instance

    Returns:
        Dictionary with structure: {category: {action: count}}
        where category is 'public'/'preview'/'internal'
        and action is 'removed'/'added'
    """
    stats = {
        "public":   {"removed": 0, "added": 0},
        "preview":  {"removed": 0, "added": 0},
        "internal": {"removed": 0, "added": 0},
    }
    for section, symbol in _iter_abidiff_symbols(stdout):
        cat = classifier.classify(symbol)
        if cat in stats:
            stats[cat][section] += 1
    return stats


def extract_symbol_lists(stdout: str, classifier: SymbolClassifier) -> Dict[str, Dict[str, List[str]]]:
    """Extract per-category lists of removed/added symbol names from abidiff output.

    Args:
        stdout: abidiff stdout output
        classifier: SymbolClassifier instance

    Returns:
        Dictionary {category: {action: [demangled_name, ...]}}
    """
    result: Dict[str, Dict[str, List[str]]] = {
        "public":   {"removed": [], "added": []},
        "preview":  {"removed": [], "added": []},
        "internal": {"removed": [], "added": []},
    }
    for section, symbol in _iter_abidiff_symbols(stdout):
        demangled = demangle_symbol(symbol) if symbol.startswith("_Z") else symbol
        cat = classifier.classify(demangled)
        if cat in result:
            result[cat][section].append(demangled)
    return result


def compare_abi(old_abi: Path, new_abi: Path, suppressions: Optional[Path] = None,
                classifier: Optional[SymbolClassifier] = None,
                verbose: bool = False) -> Tuple[int, Dict, str]:
    """Compare two ABI baselines using abidiff.

    Args:
        old_abi: Path to old baseline .abi file
        new_abi: Path to new baseline .abi file
        suppressions: Optional path to suppressions file
        classifier: Optional SymbolClassifier for categorizing changes
        verbose: Enable verbose output

    Returns:
        Tuple of (exit_code, stats_dict)
    """
    cmd = ["abidiff"]
    if suppressions and suppressions.exists():
        cmd.extend(["--suppressions", str(suppressions)])
    cmd.extend([str(old_abi), str(new_abi)])
    if verbose:
        print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if verbose and result.stderr:
        print(f"  stderr: {result.stderr[:500]}")
    if classifier:
        stats = parse_abidiff_symbols(result.stdout, classifier)
    else:
        stats = {"public": {"removed": 0, "added": 0}}
        for line in result.stdout.splitlines():
            if "Function symbols changes summary:" in line:
                parts = line.replace(",", "").split()
                try:
                    stats["public"]["removed"] = int(parts[parts.index("Removed") - 1])
                    stats["public"]["added"]   = int(parts[parts.index("Added")   - 1])
                except (ValueError, IndexError):
                    pass
    return result.returncode, stats, result.stdout


def print_details(stdout: str, old_ver: str, new_ver: str,
                  classifier: SymbolClassifier, limit: int = 10) -> None:
    """Print detailed removed/added public symbol names for a version pair."""
    lists = extract_symbol_lists(stdout, classifier)

    print(f"\n  {old_ver} → {new_ver}")
    for cat in ("public", "preview", "internal"):
        removed = lists[cat]["removed"]
        added   = lists[cat]["added"]
        if not removed and not added:
            continue
        
        print(f"  [{cat.upper()}]")
        
        def print_grouped(items, action_name):
            grouped = defaultdict(list)
            for s in items:
                grouped[extract_namespace(s)].append(s)
            
            print(f"    {action_name} ({len(items)}):")
            for ns, syms in sorted(grouped.items()):
                print(f"      {ns}:")
                for s in syms[:limit]:
                    print(f"        - {s[:78]}")
                if len(syms) > limit:
                    print(f"        … +{len(syms)-limit} more in {ns}")

        if removed:
            print_grouped(removed, "Removed")
        if added:
            print_grouped(added, "Added")


def main():
    """Main entry point for ABI comparison workflow."""
    parser = argparse.ArgumentParser(description="Compare ABI across all package versions")
    parser.add_argument("channel", help="Conda channel (e.g., conda-forge)")
    parser.add_argument("package", help="Package name (e.g., dal)")
    default_cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "abi_cache"
    parser.add_argument("--cache-dir",      default=str(default_cache))
    parser.add_argument("--devel-package",  help="Development package (e.g., dal-devel)")
    parser.add_argument("--headers-subdir", default="include")
    parser.add_argument("--suppressions",   help="Suppressions file path")
    parser.add_argument("--track-preview",  action="store_true", help="Track preview/experimental separately")
    parser.add_argument("--details",        action="store_true", help="Show symbol names for breaking pairs")
    parser.add_argument("--details-limit",  type=int, default=10, help="Max symbols per category (default: 10)")
    parser.add_argument("--json",           help="Path to save results in JSON format")
    parser.add_argument("--verbose",        action="store_true")

    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    classifier = SymbolClassifier() if args.track_preview or getattr(args, "details", False) or getattr(args, "json", False) else None

    print(f"Fetching versions for {args.channel}:{args.package}...")
    versions = get_package_versions(args.channel, args.package)
    if not versions:
        print("No versions found")
        return 1

    print(f"Total versions: {len(versions)}")
    print(f"Total comparisons: {len(versions)-1}")
    if args.devel_package:
        print(f"Using devel package: {args.devel_package}")
    if args.track_preview:
        print("Tracking preview/experimental API separately")
    print()

    results = []
    for i in range(len(versions) - 1):
        old_ver, new_ver = versions[i], versions[i+1]
        if args.verbose:
            print(f"\nProcessing {old_ver} → {new_ver}")

        old_abi = cache_dir / f"{args.package}_{old_ver}.abi"
        new_abi = cache_dir / f"{args.package}_{new_ver}.abi"

        for ver, abi_path in [(old_ver, old_abi), (new_ver, new_abi)]:
            if abi_path.exists():
                if args.verbose:
                    print(f"  Cached: {abi_path.name}")
                continue
            with tempfile.TemporaryDirectory(prefix="abi_env_") as tmpdir:
                env_path = Path(tmpdir) / "env"
                if not download_packages(args.channel, args.package, ver, env_path,
                                         args.devel_package, args.verbose):
                    continue
                lib = find_library(env_path, args.package, args.verbose)
                if not lib:
                    if args.verbose:
                        print(f"  Library not found for {ver}")
                    continue
                headers = env_path / args.headers_subdir if args.devel_package else None
                sup = Path(args.suppressions) if args.suppressions else None
                if not generate_abi_baseline(lib, abi_path, headers, sup, args.verbose):
                    continue

        if not old_abi.exists() or not new_abi.exists():
            print(f"?(3) | {old_ver} → {new_ver} | baselines missing")
            results.append({"old": old_ver, "new": new_ver, "exit_code": 3,
                             "stats": {"public": {"removed": 0, "added": 0}},
                             "old_abi": str(old_abi), "new_abi": str(new_abi)})
            continue

        sup = Path(args.suppressions) if args.suppressions else None
        exit_code, stats, diff_stdout = compare_abi(old_abi, new_abi, sup,
                                       classifier if args.track_preview else None,
                                       args.verbose)
        status = {0:"✅ NO_CHANGE", 4:"✅ COMPATIBLE", 8:"⚠️  INCOMPAT", 12:"❌ BREAKING"}.get(exit_code, f"?({exit_code})")
        pub = stats.get("public", {"removed": 0, "added": 0})
        line = f"{status} | {old_ver} → {new_ver} | public: -{pub['removed']} +{pub['added']}"
        if args.track_preview:
            prv = stats.get("preview",  {"removed": 0, "added": 0})
            itn = stats.get("internal", {"removed": 0, "added": 0})
            line += f" | preview: -{prv['removed']} +{prv['added']} | internal: -{itn['removed']} +{itn['added']}"
        print(line)
        results.append({"old": old_ver, "new": new_ver, "exit_code": exit_code,
                         "stats": stats, "old_abi": str(old_abi), "new_abi": str(new_abi), "stdout": diff_stdout})

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    breaking = [r for r in results if r["exit_code"] == 12]
    compat   = [r for r in results if r["exit_code"] == 4]
    no_change= [r for r in results if r["exit_code"] == 0]
    print(f"✅ NO_CHANGE:  {len(no_change)}")
    print(f"✅ COMPATIBLE: {len(compat)}")
    print(f"❌ BREAKING:   {len(breaking)}")
    if breaking:
        print("\nBreaking changes (public API):")
        for r in breaking:
            pub = r["stats"].get("public", {"removed": 0, "added": 0})
            print(f"  {r['old']} → {r['new']} (public: -{pub['removed']} +{pub['added']})")

    # Details
    if args.details and breaking:
        print()
        print("=" * 60)
        print(f"DETAILS (top {args.details_limit} symbols per category per namespace)")
        print("=" * 60)
        for r in breaking:
            print_details(r["stdout"], r["old"], r["new"],
                          classifier, args.details_limit)

    # JSON Output
    if args.json:
        json_path = Path(args.json)
        json_data = {
            "channel": args.channel,
            "package": args.package,
            "comparisons": []
        }
        for r in results:
            comp = {
                "old_version": r["old"],
                "new_version": r["new"],
                "exit_code": r["exit_code"],
                "status": {0: "NO_CHANGE", 4: "COMPATIBLE", 8: "INCOMPATIBLE", 12: "BREAKING"}.get(r["exit_code"], f"UNKNOWN({r['exit_code']})"),
                "stats": r["stats"]
            }
            if r.get("stdout") and r["exit_code"] in (8, 12):
                lists = extract_symbol_lists(r["stdout"], classifier)
                comp["symbols"] = {}
                for cat in ("public", "preview", "internal"):
                    comp["symbols"][cat] = {
                        "removed": lists[cat]["removed"],
                        "added": lists[cat]["added"]
                    }
            json_data["comparisons"].append(comp)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
        print(f"\nSaved results to {json_path}")


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
