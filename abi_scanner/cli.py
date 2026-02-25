"""CLI interface for abi-scanner."""

import json
import shutil
import subprocess
import sys
import tempfile
import argparse
from pathlib import Path
from typing import Optional

from .package_spec import PackageSpec
from .sources import create_source
from .analyzer import ABIAnalyzer, PublicAPIFilter





def _find_library(search_dir: Path, library_name: Optional[str],
                  package: str, verbose: bool = False) -> Optional[Path]:
    """Find a shared library (.so) inside an extracted package directory."""
    patterns = []
    if library_name:
        base = library_name.replace(".so", "").lstrip("lib")
        patterns = [library_name + "*", f"lib{base}.so*"]
    else:
        patterns = [f"lib{package}.so*", f"lib{package.replace('-', '_')}.so*"]

    for pat in patterns:
        cands = [
            p for p in search_dir.rglob(pat)
            if p.is_file()
            and not p.name.endswith(".py")
            and "debug" not in str(p)
            and "preview" not in p.name
        ]
        if cands:
            # prefer most-versioned name (longest)
            chosen = sorted(cands, key=lambda p: len(p.name))[-1]
            if verbose:
                print(f"  Found: {chosen}", file=sys.stderr)
            return chosen
    return None


def _generate_baseline(lib_path: Path, output_path: Path,
                        verbose: bool = False) -> bool:
    """Run abidw on a library and save the .abi baseline."""
    abidw = shutil.which("abidw")
    if not abidw:
        print("Error: abidw not found in PATH", file=sys.stderr)
        return False

    cmd = [abidw, "--out-file", str(output_path), str(lib_path)]
    # Note: suppressions apply only to abidiff, not abidw
    if verbose:
        print(f"  abidw: {lib_path.name}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  abidw failed: {result.stderr[-200:]}", file=sys.stderr)
        return False
    return True


def _download_and_prepare(spec: PackageSpec, work_dir: Path,
                           library_name: Optional[str],
                           verbose: bool = False) -> Optional[Path]:
    """Download, extract, and find the target library for a package spec.

    Returns path to the .so file, or None on failure.
    """
    source = create_source(spec)

    # Local: bare .so or directory → use directly; archives → extract first
    if spec.channel == "local":
        local_path = spec.path
        _archive_exts = {".deb", ".conda", ".gz", ".bz2", ".xz", ".zip"}
        if local_path.is_file() and local_path.suffix in _archive_exts:
            local_extract_dir = work_dir / "extract"
            local_extract_dir.mkdir(parents=True, exist_ok=True)
            extracted = source.extract(local_path, local_extract_dir)
            return _find_library(extracted, library_name, spec.package, verbose)
        return local_path  # .so file or pre-extracted directory

    download_dir = work_dir / "download"
    extract_dir = work_dir / "extract"
    download_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    # Conda channels: create temp env and locate library directly
    if spec.channel in {"conda-forge", "intel"}:
        mm = source.executable  # CondaSource stores the resolved micromamba path
        env_path = work_dir / "env"
        channel = source.channel
        cmd = [mm, "create", "-y", "-p", str(env_path), "-c", channel, f"{spec.package}={spec.version}"]
        if verbose:
            print(f"  Creating env: {' '.join(cmd)}", file=sys.stderr)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  Conda create failed: {r.stderr[-300:]}", file=sys.stderr)
            return None
        lib = _find_library(env_path, library_name, spec.package, verbose)
        if not lib:
            print(f"  Library not found in env for {spec}", file=sys.stderr)
        return lib

    # APT: resolve .deb URL via AptSource.resolve_url(), then download
    if spec.channel == "apt":
        try:
            full_url = source.resolve_url(spec.package, spec.version)
        except ValueError as e:
            print(f"  APT: {e}", file=sys.stderr)
            return None
        if verbose:
            print(f"  Downloading {full_url} ...", file=sys.stderr)
        try:
            pkg_file = source.download(full_url, spec.version, download_dir)
        except Exception as e:
            print(f"  APT download failed: {e}", file=sys.stderr)
            return None
    else:
        try:
            if verbose:
                print(f"  Downloading {spec}...", file=sys.stderr)
            pkg_file = source.download(spec.package, spec.version, download_dir)
        except Exception as e:
            print(f"  Download failed: {e}", file=sys.stderr)
            return None

    try:
        extracted = source.extract(pkg_file, extract_dir)
    except Exception as e:
        print(f"  Extraction failed: {e}", file=sys.stderr)
        return None

    lib = _find_library(extracted, library_name, spec.package, verbose)
    if not lib:
        print(f"  Library not found in {spec} (tried library_name={library_name!r}, package={spec.package!r})",
              file=sys.stderr)
    return lib


def cmd_compare(args):
    """Execute compare command."""
    try:
        old_spec = PackageSpec.parse(args.old)
        new_spec = PackageSpec.parse(args.new)

        if args.verbose:
            print(f"Comparing {old_spec} → {new_spec}", file=sys.stderr)

        library_name: Optional[str] = getattr(args, "library_name", None)
        suppressions: Optional[Path] = Path(args.suppressions) if args.suppressions else None

        with tempfile.TemporaryDirectory(prefix="abi_scanner_") as tmpdir:
            tmp = Path(tmpdir)

            # Prepare old version
            old_lib = _download_and_prepare(old_spec, tmp / "old", library_name, args.verbose)
            if not old_lib:
                print(f"Error: could not obtain library for {old_spec}", file=sys.stderr)
                return 1

            # Prepare new version
            new_lib = _download_and_prepare(new_spec, tmp / "new", library_name, args.verbose)
            if not new_lib:
                print(f"Error: could not obtain library for {new_spec}", file=sys.stderr)
                return 1

            # Generate ABI baselines
            old_abi = tmp / "old.abi"
            new_abi = tmp / "new.abi"

            if not _generate_baseline(old_lib, old_abi, args.verbose):
                print("Error: abidw failed for old version", file=sys.stderr)
                return 1
            if not _generate_baseline(new_lib, new_abi, args.verbose):
                print("Error: abidw failed for new version", file=sys.stderr)
                return 1

            # Compare
            analyzer = ABIAnalyzer(suppressions=suppressions)
            api_filter = PublicAPIFilter()
            result = analyzer.compare(old_abi, new_abi, api_filter, api_filter)

        # Output
        if args.format == "json":
            output = json.dumps(result.to_dict(), indent=2)
        else:
            verdict_map = {0: "✅ NO_CHANGE", 4: "✅ COMPATIBLE",
                           8: "⚠️  INCOMPATIBLE", 12: "❌ BREAKING"}
            verdict = verdict_map.get(result.exit_code, f"rc={result.exit_code}")
            lines = [
                f"Comparing {old_spec} → {new_spec}",
                f"Status: {verdict}",
            ]
            if result.functions_removed or result.functions_added or result.functions_changed:
                lines.append(
                    f"Functions: -{result.functions_removed} +{result.functions_added} ~{result.functions_changed}"
                )
            if result.variables_removed or result.variables_added or result.variables_changed:
                lines.append(
                    f"Variables: -{result.variables_removed} +{result.variables_added} ~{result.variables_changed}"
                )
            details = result.format_details()
            if details:
                lines.append(details)
            output = "\n".join(lines)

        if args.output:
            Path(args.output).write_text(output)
        else:
            print(output)

        # Exit code
        if args.fail_on == "breaking" and (result.exit_code & 8):
            return result.exit_code
        if args.fail_on == "any" and result.exit_code > 0:
            return result.exit_code
        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        if args.verbose:
            raise
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_compatible(args):
    print(f"Finding compatible versions for {args.spec}")
    print("(not yet implemented)")
    return 1


def cmd_validate(args):
    print(f"Validating SemVer compliance for {args.spec}")
    print("(not yet implemented)")
    return 1


def cmd_list(args):
    print(f"Listing versions for {args.spec}")
    print("(not yet implemented)")
    return 1


def create_parser():
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="abi-scanner",
        description="ABI Scanner — Universal ABI compatibility checker for C/C++ libraries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare two Intel conda versions
  abi-scanner compare intel:dal=2025.9.0 intel:dal=2025.10.0

  # Compare with local build
  abi-scanner compare conda-forge:dal=2025.9.0 local:./libonedal.so

  # APT package comparison
  abi-scanner compare apt:intel-oneapi-ccl=2021.14.0 apt:intel-oneapi-ccl=2021.15.0

  # JSON output for CI
  abi-scanner compare --format json intel:dal=2025.9.0 intel:dal=2025.10.0

Exit codes:
  0  = No ABI changes
  4  = Additions only (compatible)
  8  = Changes (possibly incompatible)
  12 = Breaking changes (removals)
"""
    )

    parser.add_argument("--version", action="version", version="%(prog)s 0.2.0-dev")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # compare
    cp = subparsers.add_parser("compare", help="Compare ABI between two package versions")
    cp.add_argument("old", help="Old package spec (channel:package=version)")
    cp.add_argument("new", help="New package spec (channel:package=version)")
    cp.add_argument("--format", choices=["text", "json"], default="text")
    cp.add_argument("--output", type=Path, help="Write output to file")
    cp.add_argument("--fail-on", choices=["breaking", "any", "none"], default="none")
    cp.add_argument("--library-name", help="Target .so filename (e.g. libsycl.so)")
    cp.add_argument("--suppressions", help="Path to abidiff suppressions file")
    cp.add_argument("-v", "--verbose", action="store_true")

    # compatible (stub)
    compat = subparsers.add_parser("compatible", help="Find compatible versions for a package")
    compat.add_argument("spec")
    compat.add_argument("--format", choices=["text", "json"], default="text")

    # validate (stub)
    val = subparsers.add_parser("validate", help="Validate SemVer compliance")
    val.add_argument("spec")
    val.add_argument("--format", choices=["text", "json"], default="text")

    # list (stub)
    lst = subparsers.add_parser("list", help="List available versions for a package")
    lst.add_argument("spec")
    lst.add_argument("--format", choices=["text", "json"], default="text")

    return parser


def main():
    """Entry point for CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    handlers = {
        "compare":    cmd_compare,
        "compatible": cmd_compatible,
        "validate":   cmd_validate,
        "list":       cmd_list,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
