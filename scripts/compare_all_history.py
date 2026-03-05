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
import shutil as _shutil

def _find_micromamba():
    """Find micromamba binary: PATH, common locations, or MAMBA_ROOT_PREFIX/bin."""
    from pathlib import Path
    for candidate in [
        _shutil.which('micromamba'),
        '/home/ubuntu/bin/micromamba',
        '/usr/local/bin/micromamba',
        str(__import__("pathlib").Path.home() / "bin" / "micromamba"),
    ]:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError('micromamba not found. Install it or add to PATH.')

_MICROMAMBA_CACHE = None

def _get_micromamba() -> str:
    global _MICROMAMBA_CACHE
    if _MICROMAMBA_CACHE is None:
        _MICROMAMBA_CACHE = _find_micromamba()
    return _MICROMAMBA_CACHE
import json
try:
    import yaml as _yaml
except ImportError:
    _yaml = None
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


# ── APT channel support ───────────────────────────────────────────────────────
import gzip as _gzip
import re as _apt_re
import urllib.request as _urllib_req

INTEL_APT_BASE = 'https://apt.repos.intel.com/oneapi'
INTEL_APT_PACKAGES_URL = INTEL_APT_BASE + '/dists/all/main/binary-amd64/Packages.gz'


def get_apt_package_versions(pkg_pattern: str,
                              apt_packages_url: str = INTEL_APT_PACKAGES_URL):
    """Fetch available versions for packages matching pkg_pattern from Intel APT.

    pkg_pattern: regex that matches package names (e.g.
        r'^intel-oneapi-compiler-dpcpp-cpp-runtime-2025\\.\\d+$').
    Returns sorted list of (version, filename) tuples.
    """
    try:
        if apt_packages_url.startswith('file://') or not apt_packages_url.startswith('http'):
            local_path = apt_packages_url.replace('file://', '')
            with open(local_path, 'rb') as _f:
                raw = _f.read()
        else:
            raw = _urllib_req.urlopen(apt_packages_url, timeout=60).read()
        if apt_packages_url.endswith('.xz'):
            import lzma as _lzma
            data = _lzma.decompress(raw).decode('utf-8', 'ignore')
        elif apt_packages_url.endswith('.gz'):
            data = _gzip.decompress(raw).decode('utf-8', 'ignore')
        else:
            data = raw.decode('utf-8', 'ignore')
    except Exception as exc:
        print(f'  APT index fetch failed: {exc}', file=sys.stderr)
        return []

    pat = _apt_re.compile(pkg_pattern)
    entries = []
    for block in data.split('\n\n'):
        pm = _apt_re.search(r'^Package: (.+)$', block, _apt_re.M)
        if not pm or not pat.match(pm.group(1)):
            continue
        vm = _apt_re.search(r'^Version: (.+)$', block, _apt_re.M)
        fm = _apt_re.search(r'^Filename: (.+)$', block, _apt_re.M)
        if vm and fm:
            entries.append((vm.group(1).strip(), fm.group(1).strip()))

    seen, rows = set(), []
    for v, f in entries:
        if v not in seen:
            seen.add(v)
            rows.append((v, f))

    def _verkey(v):
        try:
            base, build = v.split('-', 1)
            build = build.split('~')[0]  # Fix #1: strip ~distro suffix
            return tuple(map(int, base.split('.'))) + (int(build),)
        except Exception:
            return (0,)

    return sorted(rows, key=lambda x: _verkey(x[0]))


def download_and_extract_apt(version: str, filename: str, cache_dir: Path,
                              apt_base: str = INTEL_APT_BASE,
                              verbose: bool = False) -> Optional[Path]:
    """Download .deb from Intel APT and extract it. Returns extract dir."""
    import subprocess as _sp
    deb_name = Path(filename).name
    deb_path = cache_dir / f'apt_{deb_name}'
    extract_dir = cache_dir / f'apt_extract_{version}'

    if not deb_path.exists():
        url = f'{apt_base}/{filename}'
        if verbose:
            print(f'  Downloading {url} ...')
        try:
            _urllib_req.urlretrieve(url, deb_path)
        except Exception as exc:
            print(f'  Download failed: {exc}', file=sys.stderr)
            return None
    elif verbose:
        print(f'  Cached deb: {deb_name}')

    if not extract_dir.exists():
        extract_dir.mkdir(parents=True)
        try:
            _sp.run(['dpkg-deb', '-x', str(deb_path), str(extract_dir)],
                    check=True, capture_output=True)
        except Exception as exc:
            print(f'  Extraction failed: {exc}', file=sys.stderr)
            import shutil as _cleanup_shutil
            _cleanup_shutil.rmtree(extract_dir, ignore_errors=True)
            return None
    return extract_dir


def find_library_apt(extract_dir: Path, library_name: str,
                     verbose: bool = False) -> Optional[Path]:
    """Find real versioned .so in extracted .deb (not symlinks, not gdb helpers)."""
    base = library_name.removesuffix('.so').removeprefix('lib')
    patterns = [
        f'{library_name}.[0-9]*',   # libccl.so.1.0
        f'lib{base}.so.[0-9]*',     # libccl.so.1.0
        library_name,               # exact match fallback
    ]
    for pat in patterns:
        cands = [
            p for p in extract_dir.rglob(pat)
            if p.is_file() and not p.is_symlink()
            and not p.name.endswith('.py') and 'debug' not in str(p)
        ]
        if cands:
            chosen = sorted(cands, key=lambda p: len(p.name))[-1]
            if verbose:
                print(f'  Found (apt): {chosen}')
            return chosen
    return None

# ─────────────────────────────────────────────────────────────────────────────
def get_package_versions(channel, package):
    """Get all available versions for a package from conda channel.

    Args:
        channel: Conda channel name (e.g., 'conda-forge')
        package: Package name (e.g., 'dal')

    Returns:
        List of version strings sorted by packaging.version.Version
    """
    result = subprocess.run(
        [_get_micromamba(), "search", "-c", channel, package, "--json"],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
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
        [_get_micromamba(), "create", "-y", "-r", str(env_path.parent / "root"),
         "-p", str(env_path), "-c", channel] + packages,
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        if verbose:
            print(f"  Failed: {result.stderr[-300:]}")
        return False
    return True


def find_library(env_path: Path, package: str, library_name: str = None, verbose: bool = False) -> Optional[Path]:
    """Find shared library (.so) in conda environment.

    Args:
        env_path: Path to conda environment
        package: Package name to locate library for
        verbose: Enable verbose output

    Returns:
        Path to library if found, None otherwise
    """
    if library_name:
        base = library_name.removesuffix('.so').removeprefix('lib')
        lib_patterns = [library_name + '*', f"lib{base}.so*"]
    else:
        lib_patterns = [f'lib{package}.so*', 'libonedal.so*']
    for pattern in lib_patterns:
        for m in env_path.glob(f"**/{pattern}"):
            if (m.suffix == ".so" or m.name.count(".so") == 1) and not m.is_symlink():
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


def _resolve_headers(devel_dir, ver, tpl):
    """Resolve headers path from template with {version}. (S3: module-level)"""
    if not tpl:
        return devel_dir
    # Try multiple version formats: full, no-build, major.minor
    _ver_stripped = ver.split("-")[0]  # e.g. 2025.0.0
    _ver_parts = _ver_stripped.split(".")
    _ver_major_minor = ".".join(_ver_parts[:2])  # e.g. 2025.0
    for v in [ver, _ver_stripped, _ver_major_minor]:
        p = devel_dir / tpl.format(version=v)
        if p.exists():
            return p
    # fallback: find any directory matching pattern
    _tpl_prefix = tpl.split("{version}")[0] if "{version}" in tpl else ""
    if _tpl_prefix:
        _candidates = list((devel_dir / _tpl_prefix).parent.glob("*")) if "{version}" in tpl else []
        if _candidates:
            return sorted(_candidates)[-1] / (tpl.split("{version}")[-1].lstrip("/") if "{version}" in tpl else "")
    fallback = devel_dir / tpl.format(version=_ver_major_minor)
    if not fallback.exists():
        import logging as _log
        _log.getLogger(__name__).warning(
            "[abicc] headers path not found for version %s: %s", ver, fallback
        )
        return devel_dir
    return fallback


def _combined_status(abidiff_ec, abicc_r, old_ver=None, new_ver=None):
    """Combine abidiff and ABICC verdicts into a single status. (S3: module-level)"""
    abidiff_status = {0: "NO_CHANGE", 4: "COMPATIBLE", 8: "INCOMPATIBLE", 12: "BREAKING"}.get(abidiff_ec, "UNKNOWN")
    if abicc_r is None or abicc_r.error:
        return abidiff_status
    has_source_break = abicc_r.source_compat < 100.0 or abicc_r.source_problems > 0
    has_binary_break = abicc_r.binary_compat < 100.0 or abicc_r.binary_problems > 0
    if has_source_break or has_binary_break:
        if abidiff_status == "BREAKING":
            return "BREAKING"
        # abidiff=COMPATIBLE/INCOMPATIBLE but ABICC found source/binary-level changes
        return "SOURCE_BREAK"
    if abidiff_status == "BREAKING":
        _pair = f"{old_ver}→{new_ver}" if old_ver and new_ver else "unknown"
        print(
            f"  [abicc] ⚠️  ELF_INTERNAL: abidiff found breaks that ABICC could not confirm ({_pair}). "
            f"Manual review recommended for template/noexcept changes.",
            file=sys.stderr
        )
        return "ELF_INTERNAL"
    return abidiff_status


def main():
    """Main entry point for ABI comparison workflow."""
    parser = argparse.ArgumentParser(description="Compare ABI across all package versions")
    parser.add_argument("channel", nargs="?", default=None, help="Conda channel (e.g., conda-forge) -- optional when --config is used")
    parser.add_argument("package", nargs="?", default=None, help="Package name (e.g., dal) -- optional when --config is used")
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
    parser.add_argument("--apt-packages-url", default=None,
                        help="Override APT Packages index URL (supports .gz and .xz)")
    parser.add_argument("--config", help="Path to package YAML config (alternative to positional args)")
    parser.add_argument("--source", default="apt", help="Source type when --config is used (e.g. apt)")
    parser.add_argument("--abicc", action="store_true", help="Also run abi-compliance-checker for type-level analysis")
    parser.add_argument("--abicc-timeout", type=int, default=None,
                        help="Override ABICC timeout in seconds (default from config or 300)")

    args = parser.parse_args()
    if not args.config and not args.channel:
        parser.error("Either positional args (channel package) or --config must be provided")

    # If --config is provided, derive channel/package/etc from YAML
    if args.config:
        if _yaml is None:
            print("PyYAML not installed — cannot use --config", file=sys.stderr)
            return 1
        with open(args.config) as _cf:
            _cfg = _yaml.safe_load(_cf)
        # Set channel from source arg
        args.channel = args.source
        # Derive package from sources section
        _src_cfg = _cfg.get("sources", {}).get(args.source, {})
        args.package = _cfg.get("library", "unknown")
        if not args.apt_pkg_pattern and _src_cfg.get("pkg_pattern"):
            args.apt_pkg_pattern = _src_cfg["pkg_pattern"]
        if not args.apt_packages_url and _src_cfg.get("apt_packages_url"):
            args.apt_packages_url = _src_cfg["apt_packages_url"]
        if not args.apt_base_url or args.apt_base_url == INTEL_APT_BASE:
            if _src_cfg.get("base_url"):
                args.apt_base_url = _src_cfg["base_url"]
        if not args.library_name:
            args.library_name = _cfg.get("primary_lib", "")
        # Store ABICC config for later use
        args._abicc_cfg = _cfg.get("abicc", {}) if args.abicc else {}
        args._lib_paths_cfg = _src_cfg.get("paths", {})
        args._cfg_version_key = _src_cfg.get("paths", {}).get("lib", "")
    else:
        args._abicc_cfg = {}
        args._lib_paths_cfg = {}
        args._cfg_version_key = ""
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    classifier = SymbolClassifier() if args.track_preview or args.details or args.json else None
    print(f"Fetching versions for {args.channel}:{args.package}...")
    apt_version_map = {}
    if args.channel == "apt":
        if not args.library_name:
            parser.error('--library-name is required for channel=apt (e.g. libsycl.so or libccl.so)')
        if args.apt_packages_url:
            apt_index_url = args.apt_packages_url
        else:
            apt_index_url = args.apt_base_url.rstrip("/") + "/dists/all/main/binary-amd64/Packages.gz"
        if not args.apt_pkg_pattern:
            parser.error('--apt-pkg-pattern is required for channel=apt (e.g. ^intel-oneapi-compiler-dpcpp-cpp-runtime-2025\\.\\d+$)')
        apt_rows = get_apt_package_versions(args.apt_pkg_pattern, apt_index_url)
        versions = [v for v,_ in apt_rows]
        apt_version_map = {v:f for v,f in apt_rows}
    else:
        versions = get_package_versions(args.channel, args.package)
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

    results = []
    abicc_extract_dirs = {}  # version -> extract_dir (for --abicc devel pkg)

    # Pre-populate abicc_extract_dirs from already-extracted devel dirs
    if args.abicc:
        for _v in versions:
            _pre_devel = cache_dir / f"apt_devel_extract_{_v}"
            if _pre_devel.exists():
                abicc_extract_dirs[_v] = _pre_devel

    if args.abicc:
        abicc_cfg = getattr(args, "_abicc_cfg", {})
        if not abicc_cfg.get("enabled", False):
            print("  [abicc] ABICC disabled in config for this product — skipping")
            args.abicc = False
        else:
            from abi_scanner.abicc_backend import AbiccBackend as _AbiccBackend
            _abicc_backend = _AbiccBackend()
            _abicc_timeout = args.abicc_timeout or abicc_cfg.get("timeout_sec", 300)
            _abicc_devel_pattern = abicc_cfg.get("devel_pkg_pattern", "")
            _abicc_headers_subpath_tpl = abicc_cfg.get("headers_subpath", "")
            _abicc_skip_headers = abicc_cfg.get("skip_headers", [])
            print(f"  [abicc] enabled, devel_pattern={_abicc_devel_pattern}")
            # S1: pre-build devel map once (avoid fetching APT index on every loop iteration)
            _abicc_devel_map = {}
            if _abicc_devel_pattern:
                _apt_idx_url = args.apt_packages_url or (args.apt_base_url.rstrip("/") + "/dists/all/main/binary-amd64/Packages.gz")
                _abicc_devel_rows = get_apt_package_versions(_abicc_devel_pattern, _apt_idx_url)
                _abicc_devel_map = {v: fn for v, fn in _abicc_devel_rows}

    for i in range(len(versions) - 1):
        old_ver, new_ver = versions[i], versions[i+1]
        if args.verbose:
            print(f"\nProcessing {old_ver} → {new_ver}")

        _lib_tag = args.library_name.replace("/", "_").replace(".", "_") if args.library_name else "all"
        old_abi = cache_dir / f"{args.package}_{_lib_tag}_{old_ver}.abi"
        new_abi = cache_dir / f"{args.package}_{_lib_tag}_{new_ver}.abi"

        for ver, abi_path in [(old_ver, old_abi), (new_ver, new_abi)]:
            if abi_path.exists():
                if args.verbose:
                    print(f"  Cached: {abi_path.name}")
                continue
            if args.channel == "apt":
                filename = apt_version_map.get(ver)
                if not filename:
                    continue
                extract_dir = download_and_extract_apt(ver, filename, cache_dir, args.apt_base_url, args.verbose)
                if not extract_dir:
                    continue
                # Also download devel package for ABICC if needed
                if args.abicc and _abicc_devel_pattern and ver not in abicc_extract_dirs:
                    _devel_fn = _abicc_devel_map.get(ver)
                    if _devel_fn:
                        # Use devel-specific extract dir (separate from runtime)
                        _deb_name = Path(_devel_fn).name
                        _deb_path = cache_dir / f"apt_{_deb_name}"
                        _devel_extract = cache_dir / f"apt_devel_extract_{ver}"
                        if not _deb_path.exists():
                            _url = f"{args.apt_base_url}/{_devel_fn}"
                            if args.verbose:
                                print(f"  [abicc] downloading devel: {_url}")
                            try:
                                _urllib_req.urlretrieve(_url, _deb_path)
                            except Exception as _de:
                                print(f"  [abicc] devel download failed: {_de}", file=sys.stderr)
                                _deb_path = None
                        if _deb_path and _deb_path.exists():
                            if not _devel_extract.exists():
                                _devel_extract.mkdir(parents=True)
                                _extract_r = subprocess.run(["dpkg-deb", "-x", str(_deb_path), str(_devel_extract)], capture_output=True)
                                if _extract_r.returncode != 0:
                                    print(f"  [abicc] dpkg-deb failed: {_extract_r.stderr.decode()[:200]}", file=sys.stderr)
                                    import shutil as _sh; _sh.rmtree(_devel_extract, ignore_errors=True)
                                else:
                                    abicc_extract_dirs[ver] = _devel_extract
                            elif _devel_extract.exists():
                                abicc_extract_dirs[ver] = _devel_extract
                                if args.verbose:
                                    print(f"  [abicc] devel extracted: {_devel_extract}")
                    else:
                        if args.verbose:
                            print(f"  [abicc] no devel pkg found for version {ver}")
                lib = find_library_apt(extract_dir, args.library_name or args.package, args.verbose)
                if not lib:
                    if args.verbose:
                        print(f"  Library not found for {ver} (apt)")
                    continue
                sup = Path(args.suppressions) if args.suppressions else None
                if not generate_abi_baseline(lib, abi_path, None, sup, args.verbose):
                    continue
            else:
                with tempfile.TemporaryDirectory(prefix="abi_env_") as tmpdir:
                    env_path = Path(tmpdir) / "env"
                    if not download_packages(args.channel, args.package, ver, env_path,
                                             args.devel_package, args.verbose):
                        continue
                    lib = find_library(env_path, args.package, library_name=args.library_name, verbose=args.verbose)
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
                                       classifier if (args.track_preview or args.json) else None,
                                       args.verbose)

        # Run ABICC if requested
        abicc_result = None
        if args.abicc:
            _old_devel = abicc_extract_dirs.get(old_ver)
            _new_devel = abicc_extract_dirs.get(new_ver)
            if _old_devel and _new_devel:
                # Libs always come from runtime extract dirs
                _rt_old = cache_dir / f"apt_extract_{old_ver}"
                _rt_new = cache_dir / f"apt_extract_{new_ver}"
                _old_lib = find_library_apt(_rt_old, args.library_name or args.package, args.verbose) if _rt_old.exists() else None
                _new_lib = find_library_apt(_rt_new, args.library_name or args.package, args.verbose) if _rt_new.exists() else None
                _old_headers = _resolve_headers(_old_devel, old_ver, _abicc_headers_subpath_tpl)
                _new_headers = _resolve_headers(_new_devel, new_ver, _abicc_headers_subpath_tpl)
                if _old_lib and _new_lib:
                    _abicc_work = cache_dir / "abicc_work"
                    try:
                        abicc_result = _abicc_backend.run(
                            old_version=old_ver, old_lib_path=_old_lib, old_headers_path=_old_headers,
                            new_version=new_ver, new_lib_path=_new_lib, new_headers_path=_new_headers,
                            library_name=args.library_name or args.package,
                            skip_headers=_abicc_skip_headers,
                            work_dir=_abicc_work,
                            timeout=_abicc_timeout,
                        )
                        if abicc_result.error:
                            print(f"  [abicc] warning: {abicc_result.error}", file=sys.stderr)
                    except Exception as _abicc_exc:
                        print(f"  [abicc] exception: {_abicc_exc}", file=sys.stderr)
                else:
                    print(f"  [abicc] libs not found for {old_ver}/{new_ver} — skipping ABICC", file=sys.stderr)
            else:
                if args.verbose:
                    print(f"  [abicc] devel dirs missing for {old_ver}/{new_ver} — skipping")

        status = {0:"✅ NO_CHANGE", 4:"✅ COMPATIBLE", 8:"⚠️  INCOMPAT", 12:"❌ BREAKING"}.get(exit_code, f"?({exit_code})")
        if args.abicc and abicc_result and abicc_result.error:
            status = status + " [ABICC:⚠️skipped]"
        elif args.abicc and not abicc_result:
            status = status + " [ABICC:⚠️skipped]"
        if args.abicc and abicc_result and not abicc_result.error:
            combined = _combined_status(exit_code, abicc_result, old_ver, new_ver)
            status_emoji = {"NO_CHANGE": "✅ NO_CHANGE", "COMPATIBLE": "✅ COMPATIBLE",
                            "INCOMPATIBLE": "⚠️ INCOMPAT", "BREAKING": "🔴 BREAKING",
                            "SOURCE_BREAK": "🟠 SOURCE_BREAK", "ELF_INTERNAL": "⚠️ ELF_INTERNAL"}.get(combined, combined)
            status = status_emoji + f" [Bin:{abicc_result.binary_compat:.1f}% Src:{abicc_result.source_compat:.1f}%]"
        pub = stats.get("public", {"removed": 0, "added": 0})
        line = f"{status} | {old_ver} → {new_ver} | public: -{pub['removed']} +{pub['added']}"
        if args.track_preview:
            prv = stats.get("preview",  {"removed": 0, "added": 0})
            itn = stats.get("internal", {"removed": 0, "added": 0})
            line += f" | preview: -{prv['removed']} +{prv['added']} | internal: -{itn['removed']} +{itn['added']}"
        print(line)
        _res = {"old": old_ver, "new": new_ver, "exit_code": exit_code,
                "stats": stats, "old_abi": str(old_abi), "new_abi": str(new_abi), "stdout": diff_stdout}
        if abicc_result and not abicc_result.error:
            _res["abicc"] = {
                "binary_compat": abicc_result.binary_compat,
                "source_compat": abicc_result.source_compat,
                "binary_problems": abicc_result.binary_problems,
                "source_problems": abicc_result.source_problems,
                "added_symbols": abicc_result.added_symbols,
                "removed_symbols": abicc_result.removed_symbols,
                "removed_symbol_names": abicc_result.removed_symbol_names[:50],
                "type_changes": abicc_result.type_changes[:30],
            }
        results.append(_res)

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
            _base_status = {0: "NO_CHANGE", 4: "COMPATIBLE", 8: "INCOMPATIBLE", 12: "BREAKING"}.get(r["exit_code"], f"UNKNOWN({r['exit_code']})")
            _ar = r.get("abicc")
            if _ar:
                _has_source_break = _ar["source_compat"] < 100.0 or _ar["source_problems"] > 0
                _has_binary_break = _ar["binary_compat"] < 100.0 or _ar["binary_problems"] > 0
                if _has_source_break or _has_binary_break:
                    _combined = "BREAKING" if _base_status == "BREAKING" else "SOURCE_BREAK"
                elif _base_status == "BREAKING":
                    _combined = "ELF_INTERNAL"
                else:
                    _combined = _base_status
            else:
                _combined = _base_status
            comp = {
                "old_version": r["old"],
                "new_version": r["new"],
                "exit_code": r["exit_code"],
                "status": _combined,
                "abidiff_status": _base_status,
                "stats": r["stats"]
            }
            if _ar:
                comp["abicc"] = _ar
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
