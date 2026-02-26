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
    """Find all versions ABI-compatible with the given base version."""
    import re as _re

    try:
        base_spec = PackageSpec.parse(args.spec)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    source = create_source(base_spec)
    library_name: Optional[str] = getattr(args, "library_name", None)
    suppressions: Optional[Path] = Path(args.suppressions) if args.suppressions else None

    # --- Gather candidate versions ----------------------------------------
    try:
        if base_spec.channel in {"conda-forge", "intel"}:
            all_versions = source.list_versions(base_spec.package)
        elif base_spec.channel == "apt":
            if not args.apt_pkg_pattern:
                print("Error: --apt-pkg-pattern required for apt channel", file=sys.stderr)
                return 1
            all_versions = [v for v, _ in source.list_versions(args.apt_pkg_pattern)]
        else:
            print(f"Error: compatible not supported for channel '{base_spec.channel}'", file=sys.stderr)
            return 1
    except RuntimeError as e:
        print(f"Error fetching versions: {e}", file=sys.stderr)
        return 1

    # Filter to versions strictly newer than base
    from packaging.version import Version, InvalidVersion

    try:
        base_ver = Version(base_spec.version)
    except InvalidVersion as e:
        print(f"Error: base version is not parseable: {e}", file=sys.stderr)
        return 1

    parsed = []
    invalid = []
    for v in all_versions:
        try:
            parsed.append((Version(v), v))
        except InvalidVersion:
            invalid.append(v)
    if invalid and args.verbose:
        print(f"Skipped unparsable versions: {', '.join(invalid)}", file=sys.stderr)
    candidates = [v for pv, v in sorted(parsed) if pv > base_ver]

    # Optional regex filter
    if args.filter:
        try:
            fre = _re.compile(args.filter)
            candidates = [v for v in candidates if fre.search(v)]
        except _re.error as e:
            print(f"Error: invalid --filter regex: {e}", file=sys.stderr)
            return 1

    if not candidates:
        print(f"No newer versions found for {base_spec}")
        return 0

    if args.verbose:
        print(f"Base: {base_spec}", file=sys.stderr)
        print(f"Checking {len(candidates)} candidate(s): {', '.join(candidates)}", file=sys.stderr)

    # --- Compare base -> each candidate, caching baselines ----------------
    results = []  # list of (version, ABI result | None)

    with tempfile.TemporaryDirectory(prefix="abi_scanner_compat_") as tmpdir:
        tmp = Path(tmpdir)

        # Prepare base version once
        base_lib = _download_and_prepare(base_spec, tmp / "base", library_name, args.verbose)
        if not base_lib:
            print(f"Error: could not obtain library for {base_spec}", file=sys.stderr)
            return 1
        base_abi = tmp / "base.abi"
        if not _generate_baseline(base_lib, base_abi, args.verbose):
            print("Error: abidw failed for base version", file=sys.stderr)
            return 1

        analyzer = ABIAnalyzer(suppressions=suppressions)
        api_filter = PublicAPIFilter()

        for idx, ver in enumerate(candidates):
            new_spec = PackageSpec(
                channel=base_spec.channel,
                package=base_spec.package,
                version=ver,
            )
            new_lib = _download_and_prepare(
                new_spec, tmp / f"v{idx}", library_name, args.verbose
            )
            if not new_lib:
                if args.verbose:
                    print(f"  Skipping {ver}: library not found", file=sys.stderr)
                results.append((ver, None))
                continue

            new_abi = tmp / f"v{idx}.abi"
            if not _generate_baseline(new_lib, new_abi, args.verbose):
                results.append((ver, None))
                continue

            result = analyzer.compare(base_abi, new_abi, api_filter, api_filter)
            results.append((ver, result))

            if args.stop_at_first_break and result.exit_code & 8:
                if args.verbose:
                    print(f"  Stopping at first incompatible version: {ver}", file=sys.stderr)
                break

    # --- Format output -------------------------------------------------------
    VERDICT = {0: "✅ NO_CHANGE", 4: "✅ COMPATIBLE", 8: "⚠️  INCOMPATIBLE", 12: "❌ BREAKING"}

    compatible = [v for v, r in results if r is not None and not (r.exit_code & 8)]
    breaking_at = next((v for v, r in results if r is not None and (r.exit_code & 8)), None)

    if args.format == "json":
        out = {
            "base": str(base_spec),
            "compatible_versions": compatible,
            "first_breaking": breaking_at,
            "details": [
                {
                    "version": v,
                    "exit_code": r.exit_code if r else None,
                    "verdict": VERDICT.get(r.exit_code, f"rc={r.exit_code}") if r else "SKIPPED",
                }
                for v, r in results
            ],
        }
        print(json.dumps(out, indent=2))
    else:
        print(f"ABI compatibility report for {base_spec}")
        print(f"{'Version':<20} {'Status'}")
        print("-" * 50)
        print(f"  {base_spec.version:<18} (base)")
        for ver, result in results:
            if result is None:
                verdict = "⚠️  SKIPPED"
            else:
                verdict = VERDICT.get(result.exit_code, f"rc={result.exit_code}")
                if result.functions_removed or result.functions_added or result.functions_changed:
                    verdict += f"  (-{result.functions_removed} +{result.functions_added} ~{result.functions_changed})"
            print(f"  {ver:<18} {verdict}")
        print()
        if compatible:
            last_compat = compatible[-1]
            print(f"Compatible range : {base_spec.version} - {last_compat}")
        if breaking_at:
            print(f"First incompatible: {breaking_at}")
        elif not args.stop_at_first_break:
            print(f"All {len(compatible)} checked version(s) are compatible.")

    # Exit code: honor --fail-on setting
    any_change = any(r is not None and r.exit_code > 0 for _, r in results)
    if args.fail_on == "breaking" and breaking_at:
        return 8
    if args.fail_on == "any" and any_change:
        return 8
    return 0


def cmd_validate(args):
    """Validate SemVer compliance over a range of consecutive versions."""
    import re as _re
    from packaging.version import Version, InvalidVersion

    RULES = {
        "patch": {"allowed_codes": {0, 4}, "strict_codes": {0},      "label": "PATCH"},
        "minor": {"allowed_codes": {0, 4}, "strict_codes": {0, 4},  "label": "MINOR"},
        "major": {"allowed_codes": {0, 4, 8, 12}, "strict_codes": {0, 4, 8, 12}, "label": "MAJOR"},
    }

    try:
        spec = PackageSpec.parse(args.spec, require_version=False)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    source = create_source(spec)
    library_name: Optional[str] = getattr(args, "library_name", None)
    suppressions: Optional[Path] = Path(args.suppressions) if args.suppressions else None

    # ── Gather versions ───────────────────────────────────────────────────────
    try:
        if spec.channel in {"conda-forge", "intel"}:
            all_versions = source.list_versions(spec.package)
        elif spec.channel == "apt":
            if not args.apt_pkg_pattern:
                print("Error: --apt-pkg-pattern required for apt channel", file=sys.stderr)
                return 1
            all_versions = [v for v, _ in source.list_versions(args.apt_pkg_pattern)]
        else:
            print(f"Error: validate not supported for channel '{spec.channel}'", file=sys.stderr)
            return 1
    except RuntimeError as e:
        print(f"Error fetching versions: {e}", file=sys.stderr)
        return 1

    # Optional regex filter (applied before from/to range)
    if args.filter:
        try:
            fre = _re.compile(args.filter)
            all_versions = [v for v in all_versions if fre.search(v)]
        except _re.error as e:
            print(f"Error: invalid --filter regex: {e}", file=sys.stderr)
            return 1

    # Parse & sort valid versions; skip unparseable
    parsed = []
    for v in all_versions:
        try:
            parsed.append((Version(v), v))
        except InvalidVersion:
            if args.verbose:
                print(f"  Skipping unparseable version: {v}", file=sys.stderr)
    parsed.sort(key=lambda t: t[0])

    # from/to version range filter
    if args.from_version:
        try:
            fv = Version(args.from_version)
            parsed = [(pv, v) for pv, v in parsed if pv >= fv]
        except InvalidVersion as e:
            print(f"Error: invalid --from-version: {e}", file=sys.stderr)
            return 1
    if args.to_version:
        try:
            tv = Version(args.to_version)
            parsed = [(pv, v) for pv, v in parsed if pv <= tv]
        except InvalidVersion as e:
            print(f"Error: invalid --to-version: {e}", file=sys.stderr)
            return 1

    if len(parsed) < 2:
        print("Not enough versions to validate (need at least 2).", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Validating {len(parsed)} versions, {len(parsed)-1} transition(s)", file=sys.stderr)

    def classify(old_pv: Version, new_pv: Version) -> str:
        """Classify transition as patch/minor/major based on version segments."""
        if old_pv.major != new_pv.major:
            return "major"
        if old_pv.minor != new_pv.minor:
            return "minor"
        return "patch"

    # ── Compare consecutive pairs ─────────────────────────────────────────────
    VERDICT = {0: "NO_CHANGE", 4: "COMPATIBLE", 8: "INCOMPATIBLE", 12: "BREAKING"}
    ICON    = {0: "✅", 4: "✅", 8: "⚠️ ", 12: "❌"}

    rows = []      # (old_v, new_v, kind, result|None, compliant)
    violations = []

    with tempfile.TemporaryDirectory(prefix="abi_scanner_val_") as tmpdir:
        tmp = Path(tmpdir)
        analyzer = ABIAnalyzer(suppressions=suppressions)
        api_filter = PublicAPIFilter()

        # Cache baselines: version_str → Path|None
        abi_cache: dict = {}

        def get_abi(ver_str: str, idx: int) -> "Optional[Path]":
            if ver_str in abi_cache:
                return abi_cache[ver_str]
            vspec = PackageSpec(
                channel=spec.channel, package=spec.package, version=ver_str
            )
            lib = _download_and_prepare(vspec, tmp / f"pkg_{idx}", library_name, args.verbose)
            if not lib:
                abi_cache[ver_str] = None
                return None
            abi_path = tmp / f"{idx}.abi"
            if not _generate_baseline(lib, abi_path, args.verbose):
                abi_cache[ver_str] = None
                return None
            abi_cache[ver_str] = abi_path
            return abi_path

        for i in range(len(parsed) - 1):
            old_pv, old_v = parsed[i]
            new_pv, new_v = parsed[i + 1]
            kind = classify(old_pv, new_pv)

            old_abi = get_abi(old_v, i * 2)
            new_abi = get_abi(new_v, i * 2 + 1)

            if old_abi is None or new_abi is None:
                rows.append((old_v, new_v, kind, None, None))
                continue

            result = analyzer.compare(old_abi, new_abi, api_filter, api_filter)

            # Compliance check
            if args.strict:
                allowed = RULES[kind]["strict_codes"] if kind == "patch" else RULES[kind]["allowed_codes"]
            else:
                allowed = RULES[kind]["allowed_codes"]

            compliant = result.exit_code in allowed
            rows.append((old_v, new_v, kind, result, compliant))

            if not compliant:
                violations.append({
                    "from": old_v, "to": new_v, "kind": kind,
                    "exit_code": result.exit_code,
                    "verdict": VERDICT.get(result.exit_code, f"rc={result.exit_code}"),
                    "functions_removed": result.functions_removed,
                    "functions_added": result.functions_added,
                })

    # ── Output ────────────────────────────────────────────────────────────────
    total = len([r for r in rows if r[3] is not None])
    ok    = len([r for r in rows if r[4] is True])

    if args.format == "json":
        out = {
            "spec": str(spec),
            "total_transitions": total,
            "compliant": ok,
            "violations": len(violations),
            "strict": args.strict,
            "rows": [
                {
                    "from": old_v, "to": new_v, "kind": kind,
                    "exit_code": r.exit_code if r else None,
                    "verdict": VERDICT.get(r.exit_code, f"rc={r.exit_code}") if r else "SKIPPED",
                    "compliant": c,
                }
                for old_v, new_v, kind, r, c in rows
            ],
            "violation_details": violations,
        }
        print(json.dumps(out, indent=2))
    else:
        mode = "strict" if args.strict else "lenient"
        print(f"SemVer compliance report — {spec}  [{mode} mode]")
        print(f"{'From':<22} {'To':<22} {'Type':<8} {'Status'}")
        print("-" * 75)
        for old_v, new_v, kind, result, compliant in rows:
            if result is None:
                line = "  SKIPPED"
            else:
                icon = ICON.get(result.exit_code, "?")
                verdict = VERDICT.get(result.exit_code, f"rc={result.exit_code}")
                flag = "" if compliant else "  ← VIOLATION"
                stats = ""
                if result.functions_removed or result.functions_added:
                    stats = f"  (-{result.functions_removed} +{result.functions_added})"
                line = f"  {icon} {kind:<8} {verdict}{stats}{flag}"
            print(f"  {old_v:<22}{new_v:<22}{line}")
        print()
        pct = int(100 * ok / total) if total else 0
        print(f"SemVer compliance: {pct}% ({ok}/{total} transitions)")
        if violations:
            print(f"Violations ({len(violations)}):")
            for v in violations:
                print(f"  ❌ {v['from']} → {v['to']}  [{v['kind'].upper()}]"
                      f"  {v['verdict']}  (-{v['functions_removed']} +{v['functions_added']})")
        else:
            print("No violations found. ✅")

    if violations and args.fail_on != "none":
        return min(len(violations), 125)  # shell exit codes capped at 255; 125 avoids signal-reserved range
    return 0


def cmd_list(args):
    """List available versions for a package spec."""
    import re as _re

    try:
        spec = PackageSpec.parse(args.spec, require_version=False)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    source = create_source(spec)

    # Fetch versions
    try:
        if spec.channel in {"conda-forge", "intel"}:
            versions = source.list_versions(spec.package)
            entries = [(v, None) for v in versions]

        elif spec.channel == "apt":
            if not args.apt_pkg_pattern:
                print(
                    "Error: --apt-pkg-pattern required for apt channel "
                    "(e.g. ^intel-oneapi-ccl-2021)",
                    file=sys.stderr,
                )
                return 1
            # Ensure pattern at least mentions the positional package name
            pkg_hint = spec.package.lower()
            pat_lower = args.apt_pkg_pattern.lower()
            if pkg_hint not in pat_lower and pkg_hint not in pat_lower.replace("\\", ""):
                print(
                    f"Warning: --apt-pkg-pattern does not appear to mention "
                    f"package '{spec.package}'; results may be unrelated.",
                    file=sys.stderr,
                )
            entries = source.list_versions(args.apt_pkg_pattern)

        else:
            print(f"Error: list not supported for channel '{spec.channel}'", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error fetching versions: {e}", file=sys.stderr)
        return 1

    if not entries:
        print(f"No versions found for {spec.channel}:{spec.package}", file=sys.stderr)
        return 1

    # Optional regex filter
    if args.filter:
        try:
            fre = _re.compile(args.filter)
        except _re.error as e:
            print(f"Error: invalid --filter regex: {e}", file=sys.stderr)
            return 1
        entries = [(v, f) for v, f in entries if fre.search(v)]

    # Output
    if args.format == "json":
        data = [{"version": v, "filename": f} for v, f in entries]
        print(json.dumps(data, indent=2))
    else:
        print(f"Versions for {spec.channel}:{spec.package} ({len(entries)} total):")
        for v, f in entries:
            suffix = f"  [{f}]" if f else ""
            print(f"  {v}{suffix}")

    return 0


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

    # compatible
    compat = subparsers.add_parser("compatible",
        help="Find all versions ABI-compatible with a given base version")
    compat.add_argument("spec", help="Base package spec (channel:package=version)")
    compat.add_argument("--format", choices=["text", "json"], default="text")
    compat.add_argument("--library-name", help="Target .so filename (e.g. libsycl.so)")
    compat.add_argument("--suppressions", help="Path to abidiff suppressions file")
    compat.add_argument("--filter", help="Regex filter on candidate version strings")
    compat.add_argument("--apt-pkg-pattern",
                        help="Regex for APT package names (required for apt channel)")
    compat.add_argument("--stop-at-first-break", action="store_true",
                        help="Stop checking as soon as first incompatible version is found")
    compat.add_argument("--fail-on", choices=["breaking", "any", "none"], default="none",
                        help="Return non-zero exit if incompatible version found")
    compat.add_argument("-v", "--verbose", action="store_true")

    # validate
    val = subparsers.add_parser("validate",
        help="Validate SemVer compliance over a range of consecutive versions")
    val.add_argument("spec", help="Package spec: channel:package (e.g. intel:oneccl-cpu)")
    val.add_argument("--format", choices=["text", "json"], default="text")
    val.add_argument("--library-name", help="Target .so filename (e.g. libccl.so)")
    val.add_argument("--suppressions", help="Path to abidiff suppressions file")
    val.add_argument("--filter", help="Regex filter on version list (e.g. ^2021.14)")
    val.add_argument("--from-version", help="Start of version range (inclusive)")
    val.add_argument("--to-version",   help="End of version range (inclusive)")
    val.add_argument("--apt-pkg-pattern",
                     help="Regex for APT package names (required for apt channel)")
    val.add_argument("--strict", action="store_true",
                     help="Patch releases must be NO_CHANGE (exit 0); default allows COMPATIBLE (exit 4)")
    val.add_argument("--fail-on", choices=["violations", "none"], default="none",
                     help="Return non-zero exit code equal to violation count")
    val.add_argument("-v", "--verbose", action="store_true")

    # list
    lst = subparsers.add_parser("list", help="List available versions for a package")
    lst.add_argument("spec", help="Package spec: channel:package (e.g. intel:oneccl-cpu)")
    lst.add_argument("--format", choices=["text", "json"], default="text")
    lst.add_argument("--filter", help="Regex to filter version list (e.g. ^2021.14)")
    lst.add_argument("--apt-pkg-pattern",
                     help="Regex for APT package names (required for apt channel)")

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
