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

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import sys

# Import shared extract_namespace to avoid duplicating regex logic
from abi_scanner.analyzer import extract_namespace
from abi_scanner.module_scanner import (
    SymbolClassifier,
    demangle_symbol,
    extract_symbol_lists,
    parse_abidiff_symbols,
)
from abi_scanner.package_spec import PackageSpec
from abi_scanner.sources.factory import create_source


# ── APT channel support ───────────────────────────────────────────────────────

INTEL_APT_BASE = 'https://apt.repos.intel.com/oneapi'


def get_available_versions(channel: str, package: str,
                           apt_pkg_pattern: Optional[str] = None,
                           apt_index_url: Optional[str] = None) -> Tuple[List[str], Dict[str, str]]:
    """Fetch sorted versions via the unified source adapter interface.

    Returns:
        versions: list of version strings
        apt_version_map: mapping version -> .deb filename (APT only, else empty)
    """
    spec = PackageSpec(channel=channel, package=package, version=None)
    source = create_source(spec)

    if channel == "apt":
        if not apt_pkg_pattern:
            raise ValueError("--apt-pkg-pattern is required for channel=apt")
        rows = source.list_versions(apt_pkg_pattern, index_url=apt_index_url)
        versions = [v for v, _filename in rows]
        apt_version_map = {v: filename for v, filename in rows}
        return versions, apt_version_map

    return source.list_versions(package), {}


# ─────────────────────────────────────────────────────────────────────────────
def find_library(extract_dir: Path, package: str, library_name: Optional[str] = None, verbose: bool = False) -> Optional[Path]:
    """Find shared library (.so) in extracted package directory.

    Args:
        extract_dir: Path to extracted package
        package: Package name
        library_name: Specific library name (optional)
        verbose: Enable verbose output
    """
    if library_name:
        base = library_name.removesuffix('.so').removeprefix('lib')
        patterns = [
            f'{library_name}.[0-9]*',   # libsycl.so.1
            f'lib{base}.so.[0-9]*',     # libsycl.so.1
            library_name,               # libsycl.so
            f'{library_name}*',         
            f"lib{base}.so*"
        ]
    else:
        patterns = [f'lib{package}.so*', 'libonedal.so*']
        
    for pat in patterns:
        cands = [
            p for p in extract_dir.rglob(pat)
            if p.is_file() and not p.is_symlink()
            and not p.name.endswith('.py') and 'debug' not in str(p)
        ]
        if cands:
            # Prefer the shortest name or exactly the right name, but here we just sort by length
            # to pick the most concrete one, actually longest is often libsycl.so.7.1.0 vs libsycl.so.7
            chosen = sorted(cands, key=lambda p: len(p.name))[-1]
            if verbose:
                print(f"  Found: {chosen}")
            return chosen
            
    # Fallback to symlinks if no real file found (some packages might only have symlinks or we are matching poorly)
    for pat in patterns:
        matches = list(extract_dir.rglob(pat))
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
    """Print detailed removed/added symbols (public, preview, internal) for a version pair."""
    lists = extract_symbol_lists(stdout, classifier)

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

    print(f"\n  {old_ver} → {new_ver}")
    for cat in ("public", "preview", "internal"):
        removed = lists[cat]["removed"]
        added   = lists[cat]["added"]
        if not removed and not added:
            continue
        
        print(f"  [{cat.upper()}]")
        
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
    parser.add_argument("--library-name",   help="Primary .so filename to analyse (e.g. libccl.so, libsycl.so)")
    parser.add_argument("--filter-version", help="Regex to filter version list (e.g. ^2021, ^2025)")
    parser.add_argument("--apt-pkg-pattern", help="Regex for APT package names when channel=apt")
    parser.add_argument("--apt-base-url", default=INTEL_APT_BASE, help="APT base URL")

    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    classifier = SymbolClassifier() if args.track_preview or args.details or args.json else None
    print(f"Fetching versions for {args.channel}:{args.package}...")
    apt_version_map = {}
    if args.channel == "apt" and not args.library_name:
        parser.error('--library-name is required for channel=apt (e.g. libsycl.so or libccl.so)')

    apt_index_url = None
    if args.channel == "apt":
        apt_index_url = args.apt_base_url.rstrip("/") + "/dists/all/main/binary-amd64/Packages.gz"

    try:
        versions, apt_version_map = get_available_versions(
            args.channel,
            args.package,
            apt_pkg_pattern=args.apt_pkg_pattern,
            apt_index_url=apt_index_url,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.filter_version:
        try:
            version_re = re.compile(args.filter_version)
        except re.error as exc:
            parser.error(f'Invalid --filter-version regex: {exc}')
        versions = [v for v in versions if version_re.search(v)]
        if apt_version_map:
            apt_version_map = {v: apt_version_map[v] for v in versions if v in apt_version_map}
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

    spec = PackageSpec(channel=args.channel, package=args.package, version=None)
    source = create_source(spec)

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
            
            try:
                if args.channel == "apt":
                    filename = apt_version_map.get(ver)
                    if not filename:
                        if args.verbose:
                            print(f"  Version {ver} not found in APT map")
                        continue
                    pkg_url = f"{args.apt_base_url.rstrip('/')}/{filename}"
                    pkg_file = source.download(pkg_url, ver, cache_dir)
                else:
                    pkg_file = source.download(args.package, ver, cache_dir)
                    
                extract_dir = cache_dir / f"extract_{args.package}_{ver}"
                lib_dir = source.extract(pkg_file, extract_dir)
                
                lib = find_library(lib_dir, args.package, library_name=args.library_name, verbose=args.verbose)
                if not lib:
                    if args.verbose:
                        print(f"  Library not found for {ver}")
                    continue
                
                headers = None
                if args.devel_package and args.channel != "apt":
                    devel_file = source.download(args.devel_package, ver, cache_dir)
                    devel_extract_dir = cache_dir / f"extract_{args.devel_package}_{ver}"
                    devel_dir = source.extract(devel_file, devel_extract_dir)
                    headers = devel_dir / args.headers_subdir
                    
                sup = Path(args.suppressions) if args.suppressions else None
                if not generate_abi_baseline(lib, abi_path, headers, sup, args.verbose):
                    continue
            except Exception as e:
                print(f"  Failed processing {ver}: {e}", file=sys.stderr)
                continue

        if not old_abi.exists() or not new_abi.exists():
            print(f"?(3) | {old_ver} → {new_ver} | baselines missing")
            results.append({"old": old_ver, "new": new_ver, "exit_code": 3,
                             "stats": {"public": {"removed": 0, "added": 0}},
                             "old_abi": str(old_abi), "new_abi": str(new_abi)})
            continue

        sup = Path(args.suppressions) if args.suppressions else None
        exit_code, stats, diff_stdout = compare_abi(old_abi, new_abi, sup,
                                       classifier if (args.track_preview or args.json) else None,
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
        json_path.parent.mkdir(parents=True, exist_ok=True)
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
            if r.get("stdout") and r["exit_code"] in (4, 8, 12):
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
