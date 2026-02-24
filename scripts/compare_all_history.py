#!/usr/bin/env python3
"""Compare ABI across all package versions."""
import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, List


class SymbolClassifier:
    """Classify symbols into public/preview/internal categories"""
    
    def __init__(self):
        self.internal_patterns = [
            r"::detail::",
            r"::backend::",
            r"::internal::",
            r"::impl::",
            r"^mkl_",
            r"^tbb::",
            r"^daal::.*::internal::",
        ]
        self.preview_patterns = [
            r"::preview::",
            r"::experimental::",
        ]
        self._internal_re = [re.compile(p) for p in self.internal_patterns]
        self._preview_re = [re.compile(p) for p in self.preview_patterns]
    
    def classify(self, symbol: str) -> str:
        """Return 'internal', 'preview', or 'public'"""
        for pattern in self._internal_re:
            if pattern.search(symbol):
                return "internal"
        for pattern in self._preview_re:
            if pattern.search(symbol):
                return "preview"
        return "public"


def get_package_versions(channel, package):
    """Get all available versions for a package from conda."""
    result = subprocess.run(
        ["micromamba", "search", "-c", channel, package, "--json"],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
    
    import json
    data = json.loads(result.stdout)
    versions = sorted(set(pkg["version"] for pkg in data.get("result", {}).get("pkgs", [])))
    
    from packaging.version import Version
    try:
        return sorted(versions, key=lambda v: Version(v))
    except:
        return sorted(versions)


def download_packages(channel: str, package: str, version: str, env_path: Path, 
                      devel_package: Optional[str] = None, verbose: bool = False) -> bool:
    """Download runtime + devel packages into environment"""
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
            print(f"  Failed to download: {result.stderr[-300:]}")
        return False
    return True


def find_library(env_path: Path, package: str, verbose: bool = False) -> Optional[Path]:
    """Find shared library in environment"""
    lib_patterns = [
        f"lib{package}.so*",
        f"libonedal.so*",  # DAL specific
    ]
    
    for pattern in lib_patterns:
        matches = list(env_path.glob(f"**/{pattern}"))
        for m in matches:
            if m.suffix == ".so" or (m.suffix and m.name.count(".so") == 1):
                if verbose:
                    print(f"  Found library: {m}")
                return m
    
    # Fallback: pick first .so.X
    for pattern in lib_patterns:
        matches = list(env_path.glob(f"**/{pattern}"))
        if matches:
            if verbose:
                print(f"  Found library (fallback): {matches[0]}")
            return matches[0]
    
    return None


def generate_abi_baseline(lib_path: Path, output_path: Path, headers_dir: Optional[Path] = None,
                          suppressions: Optional[Path] = None, verbose: bool = False) -> bool:
    """Generate ABI baseline using abidw"""
    cmd = ["abidw", "--out-file", str(output_path)]
    
    if headers_dir and headers_dir.exists():
        cmd.extend(["--headers-dir", str(headers_dir)])
        if verbose:
            print(f"  Using headers: {headers_dir}")
    elif verbose and headers_dir:
        print(f"  Warning: headers not found: {headers_dir}")
    
    if suppressions and suppressions.exists():
        cmd.extend(["--suppressions", str(suppressions)])
    
    cmd.append(str(lib_path))
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    if result.returncode != 0:
        if verbose:
            print(f"  abidw failed: {result.stderr[-300:]}")
        return False
    return True


def parse_abidiff_symbols(stdout: str, classifier: SymbolClassifier) -> Dict[str, Dict[str, int]]:
    """Parse abidiff output and classify symbols"""
    stats = {
        "public": {"removed": 0, "added": 0},
        "preview": {"removed": 0, "added": 0},
        "internal": {"removed": 0, "added": 0},
    }
    
    current_section = None
    for line in stdout.splitlines():
        line = line.strip()
        
        if "Removed function symbols" in line:
            current_section = "removed"
        elif "Added function symbols" in line:
            current_section = "added"
        elif line.startswith("[D]") or line.startswith("[A]"):
            symbol = line.split(maxsplit=1)[1] if len(line.split(maxsplit=1)) > 1 else ""
            category = classifier.classify(symbol)
            if current_section and category in stats:
                stats[category][current_section] += 1
    
    return stats


def compare_abi(old_abi: Path, new_abi: Path, suppressions: Optional[Path] = None,
                classifier: Optional[SymbolClassifier] = None, verbose: bool = False) -> Tuple[int, Dict]:
    """Compare two ABI baselines"""
    cmd = ["abidiff"]
    if suppressions and suppressions.exists():
        cmd.extend(["--suppressions", str(suppressions)])
    cmd.extend([str(old_abi), str(new_abi)])
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    # Parse with classifier
    if classifier:
        stats = parse_abidiff_symbols(result.stdout, classifier)
    else:
        # Fallback: simple counting
        stats = {"public": {"removed": 0, "added": 0}}
        for line in result.stdout.splitlines():
            if "Function symbols changes summary:" in line:
                parts = line.replace(",", "").split()
                try:
                    ridx = parts.index("Removed")
                    aidx = parts.index("Added")
                    stats["public"]["removed"] = int(parts[ridx - 1])
                    stats["public"]["added"] = int(parts[aidx - 1])
                except (ValueError, IndexError):
                    pass
    
    return result.returncode, stats


def main():
    parser = argparse.ArgumentParser(description="Compare ABI across all package versions")
    parser.add_argument("channel", help="Conda channel (e.g., conda-forge)")
    parser.add_argument("package", help="Package name (e.g., dal)")
    parser.add_argument("--cache-dir", default="/tmp/abi_cache", help="Cache directory")
    parser.add_argument("--devel-package", help="Development package name (e.g., dal-devel)")
    parser.add_argument("--headers-subdir", default="include", help="Headers subdirectory in package")
    parser.add_argument("--suppressions", help="Suppressions file path")
    parser.add_argument("--track-preview", action="store_true", help="Track preview/experimental API separately")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    classifier = SymbolClassifier() if args.track_preview else None
    
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
        
        # Generate baselines if not cached
        for ver, abi_path in [(old_ver, old_abi), (new_ver, new_abi)]:
            if abi_path.exists():
                if args.verbose:
                    print(f"  Using cached: {abi_path.name}")
                continue
            
            with tempfile.TemporaryDirectory(prefix="abi_env_") as tmpdir:
                env_path = Path(tmpdir) / "env"
                
                if not download_packages(args.channel, args.package, ver, env_path,
                                        args.devel_package, args.verbose):
                    break
                
                lib = find_library(env_path, args.package, args.verbose)
                if not lib:
                    if args.verbose:
                        print(f"  Library not found for {ver}")
                    break
                
                headers = env_path / args.headers_subdir if args.devel_package else None
                suppressions = Path(args.suppressions) if args.suppressions else None
                
                if not generate_abi_baseline(lib, abi_path, headers, suppressions, args.verbose):
                    break
        
        # Compare
        if not old_abi.exists() or not new_abi.exists():
            status = "?(3)"
            stats = {"public": {"removed": 0, "added": 0}}
            exit_code = 3
        else:
            suppressions = Path(args.suppressions) if args.suppressions else None
            exit_code, stats = compare_abi(old_abi, new_abi, suppressions, classifier, args.verbose)
            
            status_map = {0: "✅ NO_CHANGE", 4: "✅ COMPATIBLE", 8: "⚠️  INCOMPAT", 12: "❌ BREAKING"}
            status = status_map.get(exit_code, f"?({exit_code})")
        
        # Format output
        pub = stats.get("public", {"removed": 0, "added": 0})
        line = f"{status} | {old_ver} → {new_ver} | public: -{pub['removed']} +{pub['added']}"
        
        if args.track_preview:
            prev = stats.get("preview", {"removed": 0, "added": 0})
            if prev["removed"] or prev["added"]:
                line += f" | preview: -{prev['removed']} +{prev['added']}"
            intern = stats.get("internal", {"removed": 0, "added": 0})
            if intern["removed"] or intern["added"]:
                line += f" | internal: -{intern['removed']} +{intern['added']}"
        
        print(line)
        results.append({"old": old_ver, "new": new_ver, "exit_code": exit_code, "stats": stats})
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    breaking = [r for r in results if r["exit_code"] == 12]
    compat = [r for r in results if r["exit_code"] == 4]
    no_change = [r for r in results if r["exit_code"] == 0]
    
    print(f"✅ NO_CHANGE:  {len(no_change)}")
    print(f"✅ COMPATIBLE: {len(compat)}")
    print(f"❌ BREAKING:   {len(breaking)}")
    
    if breaking:
        print("\nBreaking changes (public API):")
        for r in breaking:
            pub = r["stats"].get("public", {"removed": 0, "added": 0})
            print(f"  {r['old']} → {r['new']} (public: -{pub['removed']} +{pub['added']})")


if __name__ == "__main__":
    main()
