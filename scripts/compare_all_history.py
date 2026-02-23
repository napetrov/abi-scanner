#!/usr/bin/env python3
"""Compare ABI across all package versions."""
import argparse
import os
import subprocess
import glob
import tempfile
from pathlib import Path

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
    
    # Sort by version
    from packaging.version import Version
    try:
        return sorted(versions, key=lambda v: Version(v))
    except:
        return sorted(versions)

def download_and_extract_abi(channel, package, version, cache_dir, verbose=False):
    """Download package and generate ABI baseline."""
    baseline_path = Path(cache_dir) / f"{package}_{version}.abi"
    
    if baseline_path.exists():
        if verbose:
            print(f"  Using cached baseline: {baseline_path}")
        return baseline_path
    
    # Create temp env
    with tempfile.TemporaryDirectory(prefix="abi_env_") as tmpdir:
        env_path = Path(tmpdir) / "env"
        
        if verbose:
            print(f"  Downloading {package}={version}...")
        
        result = subprocess.run(
            ["micromamba", "create", "-y", "-r", tmpdir, "-p", str(env_path),
             "-c", channel, f"{package}={version}"],
            capture_output=True, text=True, check=False
        )
        
        if result.returncode != 0:
            if verbose:
                print(f"  Failed to download: {result.stderr}")
            return None
        
        # Find library
        lib_patterns = [
            f"lib{package}.so*",
            f"libonedal.so*",  # DAL specific
        ]
        
        lib_file = None
        for pattern in lib_patterns:
            matches = list(env_path.glob(f"**/{pattern}"))
            # Find actual .so (not .so.X)
            for m in matches:
                if m.suffix == ".so" or (m.suffix and m.name.count(".so") == 1):
                    lib_file = m
                    break
            if lib_file:
                break
        
        if not lib_file:
            # Fallback: pick first .so.X file
            for pattern in lib_patterns:
                matches = list(env_path.glob(f"**/{pattern}"))
                if matches:
                    lib_file = matches[0]
                    break
        
        if not lib_file:
            if verbose:
                print(f"  No library found for {package}={version}")
            return None
        
        if verbose:
            print(f"  Found library: {lib_file.name}")
            print(f"  Generating ABI baseline...")
        
        result = subprocess.run(
            ["abidw", "--out-file", str(baseline_path), str(lib_file)],
            capture_output=True, text=True, check=False
        )
        
        if result.returncode != 0:
            if verbose:
                print(f"  abidw failed: {result.stderr}")
            return None
    
    return baseline_path

def compare_abi(old_abi, new_abi, suppressions=None, verbose=False):
    """Run abidiff and return results."""
    cmd = ["abidiff"]
    if suppressions and Path(suppressions).exists():
        cmd.extend(["--suppressions", suppressions])
    cmd.extend([str(old_abi), str(new_abi)])
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    # Parse summary
    removed = added = 0
    for line in result.stdout.splitlines():
        if "Function symbols changes summary:" in line:
            parts = line.split()
            try:
                idx_removed = parts.index("Removed,")
                idx_added = parts.index("Added")
                removed = int(parts[idx_removed - 1])
                added = int(parts[idx_added - 1])
            except (ValueError, IndexError):
                pass
    
    return result.returncode, removed, added, result.stdout

def main():
    parser = argparse.ArgumentParser(description="Compare ABI across all package versions")
    parser.add_argument("channel", help="Conda channel (e.g., conda-forge)")
    parser.add_argument("package", help="Package name (e.g., dal)")
    parser.add_argument("--cache-dir", default="/tmp/abi_cache", help="Cache directory for baselines")
    parser.add_argument("--suppressions", help="Path to suppressions file (optional)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Fetching versions for {args.channel}:{args.package}...")
    versions = get_package_versions(args.channel, args.package)
    
    if not versions:
        print("No versions found")
        return 1
    
    print(f"Total versions: {len(versions)}")
    print(f"Total comparisons: {len(versions)-1}")
    print()
    
    results = []
    
    for i in range(len(versions) - 1):
        old_ver = versions[i]
        new_ver = versions[i+1]
        
        if args.verbose:
            print(f"Processing {old_ver} → {new_ver}")
        
        old_abi = download_and_extract_abi(args.channel, args.package, old_ver, cache_dir, args.verbose)
        new_abi = download_and_extract_abi(args.channel, args.package, new_ver, cache_dir, args.verbose)
        
        if not old_abi or not new_abi:
            status = "?(3)"
            removed = added = 0
        else:
            exit_code, removed, added, output = compare_abi(old_abi, new_abi, args.suppressions, args.verbose)
            status = {
                0: "✅ NO_CHANGE",
                4: "✅ COMPATIBLE",
                8: "⚠️  INCOMPAT",
                12: "❌ BREAKING"
            }.get(exit_code, f"?({exit_code})")
        
        line = f"{status} | {old_ver} → {new_ver} | removed={removed} added={added}"
        print(line)
        results.append({
            "old": old_ver,
            "new": new_ver,
            "exit_code": exit_code if old_abi and new_abi else 3,
            "removed": removed,
            "added": added
        })
    
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
        print("\nBreaking changes:")
        for r in breaking:
            print(f"  {r['old']} → {r['new']} (removed={r['removed']}, added={r['added']})")

if __name__ == "__main__":
    main()
