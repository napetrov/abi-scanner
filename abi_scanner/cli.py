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
from .sources.apt import normalize_debian_version
from .analyzer import ABIAnalyzer, PublicAPIFilter, ABIVerdict, ABIComparisonResult, demangle_symbol, classify_symbol_tier





def _find_libraries(search_dir: Path, library_name: Optional[str],
                    verbose: bool = False) -> dict[str, Path]:
    """Find shared libraries (.so) inside an extracted package directory.
    Returns a dict mapping base library names (e.g. 'libmkl_rt.so') to the actual file path.
    """
    import collections
    
    found_libs = collections.defaultdict(list)
    
    # If a specific library_name is requested, we only look for that one (or its pattern)
    if library_name:
        base = library_name.replace(".so", "").lstrip("lib")
        patterns = [library_name + "*", f"lib{base}.so*"]
        cands = []
        for pat in patterns:
            cands.extend(search_dir.rglob(pat))
    else:
        # Look for all .so files
        cands = list(search_dir.rglob("*.so*"))
        
    for p in cands:
        if not p.is_file():
            continue
        if p.name.endswith(".py") or p.name.endswith(".a") or p.name.endswith(".la"):
            continue
        if "debug" in str(p).lower():
            continue
        if "preview" in p.name.lower():
            continue
        
        # Determine the base name (e.g. libmkl_rt.so.2 -> libmkl_rt.so)
        name = p.name
        idx = name.find(".so")
        if idx == -1:
            continue
        base_name = name[:idx+3]
        
        # If specific library was requested, enforce match
        if library_name and base_name != library_name:
            continue
            
        found_libs[base_name].append(p)
        
    result = {}
    for base_name, paths in found_libs.items():
        # prefer most-versioned name (longest) or longest path if tied
        chosen = sorted(paths, key=lambda p: (len(p.name), len(str(p))))[-1]
        result[base_name] = chosen
        if verbose:
            print(f"  Found {base_name}: {chosen}", file=sys.stderr)
            
    return result


def _generate_baseline(lib_path: Path, output_path: Path,
                        verbose: bool = False,
                        headers_dir: Optional[Path] = None) -> "tuple[bool, str]":
    """Run abidw on a library and save the .abi baseline.

    Returns (success, failure_reason). failure_reason is empty on success.
    Captures abidw stderr to diagnose crashes (e.g. libabigail DWARF assertion).

    Args:
        headers_dir: Optional path to -dev package include dir; passed via
            --hd1 to abidw for accurate public/private symbol separation.
    """
    abidw = shutil.which("abidw")
    if not abidw:
        return False, "abidw not found in PATH"

    cmd = [abidw, "--out-file", str(output_path)]
    if headers_dir and headers_dir.is_dir():
        cmd.extend(["--headers-dir1", str(headers_dir)])
    cmd.append(str(lib_path))
    if verbose:
        print(f"  abidw: {lib_path.name}" + (f" (headers: {headers_dir})" if headers_dir else ""),
              file=sys.stderr)

    r = subprocess.run(cmd, capture_output=True, text=True)
    # abidw may exit 0 but crash via assertion (libabigail DWARF bug) — check output file too
    if r.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        stderr_tail = r.stderr.strip()[-300:] if r.stderr.strip() else "(no output)"
        reason = f"abidw rc={r.returncode}: {stderr_tail}"
        print(f"  abidw failed [{lib_path.name}]: {stderr_tail}", file=sys.stderr)
        return False, reason
    return True, ""


def _parse_spec_parts(spec) -> tuple[str, str]:
    """Return (channel, package) from a PackageSpec or spec string."""
    spec_str = str(spec)
    if ":" in spec_str:
        return spec_str.split(":", 1)
    return "unknown", spec_str


def _download_and_prepare(spec: PackageSpec, work_dir: Path,
                           library_name: Optional[str],
                           verbose: bool = False,
                           apt_index_url: Optional[str] = None,
                           with_dev_package: bool = False) -> dict[str, Path]:
    """Download, extract, and find target libraries for a package spec.

    Returns dict mapping base names to .so file paths. Returns empty dict on failure.
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
            return _find_libraries(extracted, library_name, verbose)
        
        if local_path.is_dir():
            return _find_libraries(local_path, library_name, verbose)
        elif local_path.is_file():
            base = local_path.name
            idx = base.find(".so")
            if idx != -1:
                base = base[:idx+3]
            return {base: local_path}
        return {}

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
            return {}
        libs = _find_libraries(env_path, library_name, verbose)
        if not libs:
            print(f"  Libraries not found in env for {spec}", file=sys.stderr)
        return libs

    # APT: resolve .deb URL via AptSource.resolve_url(), then download
    if spec.channel == "apt":
        try:
            full_url = source.resolve_url(spec.package, spec.version,
                                          index_url=apt_index_url)
        except ValueError as e:
            print(f"  APT: {e}", file=sys.stderr)
            return {}
        if verbose:
            print(f"  Downloading {full_url} ...", file=sys.stderr)
        try:
            pkg_file = source.download(full_url, spec.version, download_dir)
        except Exception as e:
            print(f"  APT download failed: {e}", file=sys.stderr)
            return {}
    else:
        try:
            if verbose:
                print(f"  Downloading {spec}...", file=sys.stderr)
            pkg_file = source.download(spec.package, spec.version, download_dir)
        except Exception as e:
            print(f"  Download failed: {e}", file=sys.stderr)
            return {}

    try:
        extracted = source.extract(pkg_file, extract_dir)
    except Exception as e:
        print(f"  Extraction failed: {e}", file=sys.stderr)
        return {}

    libs = _find_libraries(extracted, library_name, verbose)
    if not libs:
        print(f"  Libraries not found in {spec} (tried library_name={library_name!r}, package={spec.package!r})",
              file=sys.stderr)
    return libs


def _is_so_file(p: Path) -> bool:
    """True if path is a .so library file rather than an .abi baseline."""
    return '.so' in p.name and not p.name.endswith('.abi')


def _symbols_only_compare(old_lib: Path, new_lib: Path) -> "Optional[ABIComparisonResult]":
    """Symbol-table diff via nm -D — fallback when abidw crashes (e.g. libabigail DWARF bug).

    Returns ABIComparisonResult with symbol-level changes. No type information.
    Result includes a note in stdout indicating this is a fallback comparison.
    """
    def _get_syms(lib: Path) -> "Optional[dict]":
        r = subprocess.run(["nm", "-D", "--defined-only", str(lib)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None
        syms: dict = {}
        for line in r.stdout.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[1] in ("T", "D", "B", "V", "W", "i", "I"):
                syms[parts[2]] = parts[1]
        return syms

    old_syms = _get_syms(old_lib)
    new_syms = _get_syms(new_lib)
    if old_syms is None or new_syms is None:
        return None

    removed = [s for s in old_syms if s not in new_syms]
    added   = [s for s in new_syms if s not in old_syms]
    changed = [s for s in old_syms if s in new_syms and old_syms[s] != new_syms[s]]

    if removed or changed:
        verdict, exit_code = ABIVerdict.BREAKING, 12
    elif added:
        verdict, exit_code = ABIVerdict.COMPATIBLE, 4
    else:
        verdict, exit_code = ABIVerdict.NO_CHANGE, 0

    return ABIComparisonResult(
        verdict=verdict,
        exit_code=exit_code,
        baseline_old=str(old_lib),
        baseline_new=str(new_lib),
        functions_removed=len(removed),
        functions_changed=len(changed),
        functions_added=len(added),
        public_removed=removed,
        public_changed=changed,
        public_added=added,
        stdout="[nm-D fallback: abidw unavailable — symbol names only, no type info]",
    )


def cmd_compare(args):
    """Execute compare command."""
    try:
        old_spec = PackageSpec.parse(args.old)
        new_spec = PackageSpec.parse(args.new)

        if args.verbose:
            print(f"Comparing {old_spec} → {new_spec}", file=sys.stderr)

        library_name: Optional[str] = getattr(args, "library_name", None)
        suppressions: Optional[Path] = Path(args.suppressions) if args.suppressions else None
        _apt_index_url: Optional[str] = getattr(args, "apt_index_url", None)
        # We always want headers if possible to do clean API+ABI separation
        _with_dev = getattr(args, "with_dev_package", True)
        _track_exp = getattr(args, "track_experimental", False)

        with tempfile.TemporaryDirectory(prefix="abi_scanner_") as tmpdir:
            tmp = Path(tmpdir)

            # Prepare old version
            old_lib = _download_and_prepare(old_spec, tmp / "old", library_name,
                                            args.verbose, apt_index_url=_apt_index_url,
                                            with_dev_package=_with_dev)
            if not old_lib:
                print(f"Error: could not obtain library for {old_spec}", file=sys.stderr)
                return 1

            # Prepare new version
            new_lib = _download_and_prepare(new_spec, tmp / "new", library_name,
                                            args.verbose, apt_index_url=_apt_index_url,
                                            with_dev_package=_with_dev)
            if not new_lib:
                print(f"Error: could not obtain library for {new_spec}", file=sys.stderr)
                return 1

            # Generate ABI baselines
            old_abi = tmp / "old.abi"
            new_abi = tmp / "new.abi"

            old_headers = getattr(old_lib, "_headers_dir", None)
            new_headers = getattr(new_lib, "_headers_dir", None)
            _ok_old, _reason_old = _generate_baseline(old_lib, old_abi, args.verbose,
                                                       headers_dir=old_headers)
            old_baseline = old_abi if _ok_old else old_lib
            _ok_new, _reason_new = _generate_baseline(new_lib, new_abi, args.verbose,
                                                       headers_dir=new_headers)
            new_baseline = new_abi if _ok_new else new_lib

            # Compare (nm-D fallback when abidw fails for either side)
            analyzer = ABIAnalyzer(suppressions=suppressions,
                             suppress_stdlib=getattr(args, "suppress_stdlib", False),
                             track_experimental=_track_exp)
            api_filter = PublicAPIFilter()
            if _is_so_file(old_baseline) or _is_so_file(new_baseline):
                if args.verbose:
                    reason = _reason_old if not _ok_old else _reason_new
                    print(f"  ⚠ abidw failed ({reason}), falling back to nm-D", file=sys.stderr)
                result = _symbols_only_compare(old_baseline, new_baseline)
                if result is None:
                    print("Error: nm-D fallback failed", file=sys.stderr)
                    return 1
            else:
                result = analyzer.compare(old_baseline, new_baseline, api_filter, api_filter)

        # Output
        if args.format == "json":
            output = json.dumps(result.to_dict(), indent=2)
        else:
            verdict_map = {
                0: "✅ NO_CHANGE",
                4: "✅ COMPATIBLE",
                8: "⚠️  INCOMPATIBLE",
                12: "❌ BREAKING"
            }
            verdict = verdict_map.get(result.verdict.value, f"rc={result.exit_code}")
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
            
            # Use ABIScanner to fetch categorized symbol delta
            # This is a stub for the future full implementation where we pass `stats`
            # For now, we will just use ABIScanner if possible
            
            details = result.format_details()
            if details:
                lines.append(details)
            output = "\n".join(lines)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output)

        # Exit code
        if args.fail_on == "breaking" and result.verdict.value >= 8: # ABIVerdict.INCOMPATIBLE
            return result.exit_code if result.exit_code > 0 else 8
        if args.fail_on == "any" and result.verdict.value > 0: # ABIVerdict.NO_CHANGE
            return result.exit_code if result.exit_code > 0 else 4
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
    _apt_index_url: Optional[str] = getattr(args, "apt_index_url", None)
    _with_dev = getattr(args, "with_dev_package", True)
    _track_exp = getattr(args, "track_experimental", False)

    # --- Gather candidate versions ----------------------------------------
    try:
        if base_spec.channel in {"conda-forge", "intel"}:
            all_versions = source.list_versions(base_spec.package)
        elif base_spec.channel == "apt":
            if not args.apt_pkg_pattern:
                args.apt_pkg_pattern = f"^{_re.escape(base_spec.package)}$"
            all_versions = [v for v, _f, _pkg in source.list_versions(
                args.apt_pkg_pattern, index_url=_apt_index_url)]
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
        base_lib = _download_and_prepare(base_spec, tmp / "base", library_name,
                                         args.verbose, apt_index_url=_apt_index_url)
        if not base_lib:
            print(f"Error: could not obtain library for {base_spec}", file=sys.stderr)
            return 1
        base_abi = tmp / "base.abi"
        _ok, _reason = _generate_baseline(base_lib, base_abi, args.verbose)
        if not _ok:
            print(f"Error: {_reason}", file=sys.stderr)
            return 1

        analyzer = ABIAnalyzer(suppressions=suppressions,
                             suppress_stdlib=getattr(args, "suppress_stdlib", False))
        api_filter = PublicAPIFilter()

        for idx, ver in enumerate(candidates):
            new_spec = PackageSpec(
                channel=base_spec.channel,
                package=base_spec.package,
                version=ver,
            )
            new_lib = _download_and_prepare(
                new_spec, tmp / f"v{idx}", library_name, args.verbose,
                apt_index_url=_apt_index_url
            )
            if not new_lib:
                if args.verbose:
                    print(f"  Skipping {ver}: library not found", file=sys.stderr)
                results.append((ver, None))
                continue

            new_abi = tmp / f"v{idx}.abi"
            _ok, _reason = _generate_baseline(new_lib, new_abi, args.verbose)
            if not _ok:
                if args.verbose:
                    print(f"  abidw failed for {ver}: {_reason}", file=sys.stderr)
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

    compatible = [v for v, r in results if r is not None and r.verdict.value < 8]
    breaking_at = next((v for v, r in results if r is not None and r.verdict.value >= 8), None)

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
                verdict = "⚠️  COMPARE_FAILED"
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


def _render_markdown_report(
    spec,
    library_name: "Optional[str]",
    rows: list,
    violations: list,
    skipped: list,
    strict: bool,
    details_limit: int,
    generated_at: str,
    VERDICT: dict,
    ICON: dict,
    source_url: "Optional[str]" = None,
) -> str:
    """Render a stable Markdown ABI compliance report."""
    import io

    total = len([r for r in rows if r[3] is not None])
    ok    = len([r for r in rows if r[4] is True])
    pct   = int(100 * ok / total) if total else 0
    mode  = "strict" if strict else "lenient"
    lib_label = library_name or "all (multi-library scan)"

    out = io.StringIO()

    def w(s: str = "") -> None:
        out.write(s + "\n")

    # ── Header ──────────────────────────────────────────────────────────────
    _channel, _pkg = _parse_spec_parts(spec)

    w("# ABI Compliance Report")
    w()
    w(f"**Channel:** `{_channel}`  ")
    w(f"**Package:** `{_pkg}`  ")
    if _channel == "apt":
        _apt_url = source_url or "https://apt.repos.intel.com/oneapi"
        w(f"**APT Index:** `{_apt_url}`  ")
    if source_url:
        w(f"**Source:** [{source_url}]({source_url})  ")
        
    # Gather all base libs for the header
    all_libs = set()
    if library_name:
        all_libs.add(library_name)
    else:
        for _ov, _nv, _k, r, _c in rows:
            if r and hasattr(r, "_lib_results"):
                all_libs.update(r._lib_results.keys())
    
    if all_libs:
        libs_list = ", ".join(f"`{x}`" for x in sorted(all_libs))
        w(f"**Libraries:** {libs_list}  ")
    else:
        w(f"**Libraries:** `{lib_label}`  ")

    w(f"**Mode:** {mode}  ")
    w(f"**Generated:** {generated_at}  ")
    w(f"**Versions scanned:** {len(rows) + 1} &nbsp;|&nbsp; "
      f"**Transitions:** {len(rows)} &nbsp;|&nbsp; "
      f"**Compliant:** {ok} &nbsp;|&nbsp; "
      f"**Violations:** {len(violations)} &nbsp;|&nbsp; "
      f"**Skipped:** {len(skipped)}")
    w()

    # ── Compliance badge ─────────────────────────────────────────────────────
    if total == 0:
        w("> ⚠️ All transitions skipped — no data.")
    elif violations:
        w(f"> ❌ **SemVer compliance: {pct}%** ({ok}/{total} transitions pass)")
    else:
        w(f"> ✅ **SemVer compliance: {pct}%** — all transitions pass")
    w()

    # ── Summary table ────────────────────────────────────────────────────────
    w("## Summary")
    w()
    w("| From | To | Type | ABI/API Status | Tool | SO-Name Change | Δ Removed | Δ Added |")
    w("|------|-----|------|--------|------|----------------|----------:|--------:|")

    _skip_map = {(sk["from"], sk["to"]): sk.get("reason", "n/a") for sk in skipped}
    for old_v, new_v, kind, result, compliant in rows:
        if result is None:
            w(f"| `{old_v}` | `{new_v}` | {kind} | ⚠️ COMPARE_FAILED | — | — | — |")
        else:
            icon  = ICON.get(result.verdict.value, "?")
            verd  = result.verdict.name
            flag  = "" if compliant else " ←"
            tool  = "nm-D" if "[nm-D fallback" in (result.stdout or "") else "abidiff"
            rem   = str(result.functions_removed) if result.functions_removed else "—"
            add   = str(result.functions_added)   if result.functions_added   else "—"
            
            so_change = "—"
            if hasattr(result, "_lib_results") and result._lib_results:
                bumps = []
                for b_name, b_res in result._lib_results.items():
                    if b_res.binary_name_old and b_res.binary_name_new and b_res.binary_name_old != b_res.binary_name_new:
                        bumps.append(f"{b_res.binary_name_old}→{b_res.binary_name_new}")
                if bumps:
                    so_change = "<br>".join(bumps)
                    
            w(f"| `{old_v}` | `{new_v}` | {kind} | {icon} {verd}{flag} | {tool} | {so_change} | {rem} | {add} |")
    w()

    # ── Violations detail ────────────────────────────────────────────────────
    w("## Violations")
    w()
    if not violations:
        w("_No violations found._ ✅")
        w()
    else:
        for v in violations:
            result = v.get("_result")
            w(f"### ❌ `{v['from']}` → `{v['to']}` &nbsp; [{v['kind'].upper()}] — {v['verdict']}")
            w()
            w(f"**Removed:** {v['functions_removed']} &nbsp; **Added:** {v['functions_added']}")
            w()

            # Per-library breakdown (multi-lib mode)
            lib_results = v.get("_lib_results", {})
            if lib_results:
                w("**Libraries affected:**")
                w()
                w("| Library | Binary Name | Verdict | Removed | Added |")
                w("|---------|-------------|---------|--------:|------:|")
                for lib_name, lr in sorted(lib_results.items()):
                    lib_icon = ICON.get(lr.exit_code, "⚠️")
                    lib_verdict = VERDICT.get(lr.exit_code, f"rc={lr.exit_code}")
                    
                    if not lr.binary_name_old and lr.binary_name_new:
                        bin_str = f"➕ `{lr.binary_name_new}`"
                    elif lr.binary_name_old and not lr.binary_name_new:
                        bin_str = f"➖ `{lr.binary_name_old}`"
                    elif lr.binary_name_old != lr.binary_name_new:
                        bin_str = f"`{lr.binary_name_old}` → `{lr.binary_name_new}`"
                    else:
                        bin_str = f"`{lr.binary_name_new}`"
                        
                    w(f"| `{lib_name}` | {bin_str} | {lib_icon} {lib_verdict} | {lr.functions_removed or '—'} | {lr.functions_added or '—'} |")
                w()

            for _section, syms_raw, label in [
                ("removed", result.public_removed if result else [], "📉 Removed symbols"),
                ("changed", result.public_changed if result else [], "🔄 Changed symbols (kind/type)"),
                ("added",   result.public_added   if result else [], "📈 Added symbols"),
            ]:
                if not syms_raw:
                    continue
                # group by tier
                by_tier: dict = {}
                for s in syms_raw:
                    dm = demangle_symbol(s)
                    tier = classify_symbol_tier(dm)
                    by_tier.setdefault(tier, []).append(dm)

                total_syms = len(syms_raw)
                w("<details>")
                w(f"<summary><b>{label}</b> ({total_syms})</summary>")
                w()
                for tier in ("public", "preview", "internal"):
                    tier_syms = by_tier.get(tier, [])
                    if not tier_syms:
                        continue
                    w(f"**{tier.capitalize()} ({len(tier_syms)}):**")
                    w()
                    # Collect corresponding raw names for stdlib-leak detection
                    raw_lookup = {demangle_symbol(s): s for s in syms_raw}
                    w("| Symbol | Tags |")
                    w("|--------|------|")
                    limit = details_limit if details_limit > 0 else len(tier_syms)
                    for sym in tier_syms[:limit]:
                        raw = raw_lookup.get(sym, sym)
                        tag = " ⚠️ `[ABI leak]`" if raw.startswith(ABIAnalyzer.STDLIB_PREFIXES) else ""
                        w(f"| `{sym.replace('|', '&#124;')}` |{tag} |")
                    if len(tier_syms) > limit:
                        w(f"| _... {len(tier_syms) - limit} more_ |")
                    w()
                w("</details>")
                w()

    # ── Skipped ──────────────────────────────────────────────────────────────
    if skipped:
        w("## Skipped Transitions")
        w()
        w("| From | To | Type | Reason |")
        w("|------|-----|------|--------|")
        for sk in skipped:
            w(f"| `{sk['from']}` | `{sk['to']}` | {sk['kind']} | {sk.get('reason', 'n/a')} |")
        w()

    # ── Footer ───────────────────────────────────────────────────────────────
    w("---")
    w(f"_Generated by [abi-scanner](https://github.com/napetrov/abi-scanner) · {generated_at}_")

    return out.getvalue()


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
    _apt_index_url: Optional[str] = getattr(args, "apt_index_url", None)

    # ── Gather versions ───────────────────────────────────────────────────────
    try:
        if spec.channel in {"conda-forge", "intel"}:
            all_versions = source.list_versions(spec.package)
        elif spec.channel == "apt":
            if not args.apt_pkg_pattern:
                args.apt_pkg_pattern = f"^{_re.escape(spec.package)}$"
            _apt_triples = source.list_versions(args.apt_pkg_pattern, index_url=_apt_index_url)
            _apt_version_to_pkg = {v: pkg for v, _f, pkg in _apt_triples}
            all_versions = [v for v, _f, _pkg in _apt_triples]
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
    # For APT channel: normalize Debian version strings (e.g. 1.3.26241~22.04 → 1.3.26241)
    # before PEP 440 parsing; original string is preserved for display/download.
    _is_apt = (spec.channel == "apt")
    parsed = []
    for v in all_versions:
        pep_v = normalize_debian_version(v) if _is_apt else v
        try:
            parsed.append((Version(pep_v), v))
        except InvalidVersion:
            if args.verbose:
                print(f"  Skipping unparseable version: {v}", file=sys.stderr)
    parsed.sort(key=lambda t: t[0])

    # from/to version range filter
    if args.from_version:
        try:
            fv = Version(normalize_debian_version(args.from_version) if _is_apt else args.from_version)
            parsed = [(pv, v) for pv, v in parsed if pv >= fv]
        except InvalidVersion as e:
            print(f"Error: invalid --from-version: {e}", file=sys.stderr)
            return 1
    if args.to_version:
        try:
            tv = Version(normalize_debian_version(args.to_version) if _is_apt else args.to_version)
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
    skipped = []   # transitions where baseline could not be generated
    violations = []

    with tempfile.TemporaryDirectory(prefix="abi_scanner_val_") as tmpdir:
        tmp = Path(tmpdir)
        analyzer = ABIAnalyzer(suppressions=suppressions,
                             suppress_stdlib=getattr(args, "suppress_stdlib", False))
        api_filter = PublicAPIFilter()

        # Cache baselines: (pkg_name, ver_str) → Path|None  (avoids aliasing when
        # different APT packages share the same version string)
        abi_cache: dict[tuple, Optional[Path]] = {}
        abi_reason_cache: dict[tuple, str] = {}

        _apt_version_to_pkg = locals().get("_apt_version_to_pkg", {})
        _with_dev = getattr(args, "with_dev_package", True)

        def get_abi(ver_str: str, idx: int) -> "Optional[dict[str, dict]]":
            pkg_name = _apt_version_to_pkg.get(ver_str, spec.package)
            key = (pkg_name, ver_str)
            if key in abi_cache:
                return abi_cache[key]
            vspec = PackageSpec(
                channel=spec.channel, package=pkg_name, version=ver_str
            )
            libs = _download_and_prepare(vspec, tmp / f"pkg_{idx}", library_name,
                                         args.verbose, apt_index_url=_apt_index_url,
                                         with_dev_package=_with_dev)
            if not libs:
                abi_cache[key] = None
                abi_reason_cache[key] = "libraries not found or download failed"
                return None
            
            result_dict = {}
            for base, lib_path in libs.items():
                abi_path = tmp / f"{idx}_{base}.abi"
                h_dir = getattr(lib_path, "_headers_dir", None)
                _ok_abi, _abidw_reason = _generate_baseline(lib_path, abi_path, args.verbose, headers_dir=h_dir)
                result_dict[base] = {
                    "so": lib_path,
                    "abi": abi_path if _ok_abi else None
                }
                    
            abi_cache[key] = result_dict
            return result_dict

        for i in range(len(parsed) - 1):
            old_pv, old_v = parsed[i]
            new_pv, new_v = parsed[i + 1]
            kind = classify(old_pv, new_pv)

            old_abi = get_abi(old_v, i * 2)
            new_abi = get_abi(new_v, i * 2 + 1)

            if old_abi is None or new_abi is None:
                if old_abi is None:
                    old_pkg = _apt_version_to_pkg.get(old_v, spec.package)
                    reason = abi_reason_cache.get((old_pkg, old_v))
                else:
                    new_pkg = _apt_version_to_pkg.get(new_v, spec.package)
                    reason = abi_reason_cache.get((new_pkg, new_v))
                skipped.append({"from": old_v, "to": new_v, "kind": kind, "reason": reason or "Download failed or library not found"})
                rows.append((old_v, new_v, kind, None, None))
                continue

            # old_abi and new_abi are now dicts: base_name -> abi_path|so_path
            all_bases = set(old_abi.keys()) | set(new_abi.keys())
            lib_results: dict[str, "ABIComparisonResult"] = {}
            worst_exit = 0
            worst_result = None

            for base in sorted(all_bases):
                if base not in new_abi:
                    r = ABIComparisonResult(
                        verdict=ABIVerdict.BREAKING,
                        exit_code=12,
                        baseline_old=str(old_abi[base]["so"]),
                        baseline_new="",
                        functions_removed=1
                    )
                elif base not in old_abi:
                    r = ABIComparisonResult(
                        verdict=ABIVerdict.COMPATIBLE,
                        exit_code=4,
                        baseline_old="",
                        baseline_new=str(new_abi[base]["so"]),
                        functions_added=1
                    )
                elif old_abi[base]["abi"] and new_abi[base]["abi"]:
                    r = analyzer.compare(old_abi[base]["abi"], new_abi[base]["abi"], api_filter, api_filter)
                else:
                    r = _symbols_only_compare(old_abi[base]["so"], new_abi[base]["so"])
                    if r is None:
                        continue
                    if args.verbose:
                        print(f"  ⚠ nm-D fallback for {base}: {old_v}→{new_v}", file=sys.stderr)

                if base in old_abi and base in new_abi:
                    r.binary_name_old = old_abi[base]["so"].name
                    r.binary_name_new = new_abi[base]["so"].name
                    
                    # SO-Name bump check
                    if r.binary_name_old != r.binary_name_new:
                        # Only break if it's not a major transition
                        if kind != "major":
                            r.verdict = ABIVerdict.BREAKING
                            if r.exit_code < 12:
                                r.exit_code = 12
                            # Append a note
                            if r.stdout is None:
                                r.stdout = ""
                            r.stdout = f"[SO-NAME BUMP IN {kind.upper()}] {r.binary_name_old} -> {r.binary_name_new}\n" + r.stdout

                lib_results[base] = r
                if r.exit_code > worst_exit:
                    worst_exit = r.exit_code
                    worst_result = r

            if worst_result is None:
                skipped.append({"from": old_v, "to": new_v, "kind": kind,
                                "reason": "Download failed or library not found"})
                rows.append((old_v, new_v, kind, None, None))
                continue

            # Attach per-lib breakdown to worst_result for use in reports
            worst_result._lib_results = lib_results

            # Compliance check using worst exit_code across all libs
            if args.strict:
                allowed = RULES[kind]["strict_codes"] if kind == "patch" else RULES[kind]["allowed_codes"]
            else:
                allowed = RULES[kind]["allowed_codes"]

            # Use the (potentially downgraded) verdict for compliance, not raw exit code
            compliant = worst_result.verdict.value in allowed
            rows.append((old_v, new_v, kind, worst_result, compliant))

            if not compliant:
                violations.append({
                    "from": old_v, "to": new_v, "kind": kind,
                    "exit_code": worst_result.exit_code,
                    "verdict": worst_result.verdict.name,
                    "functions_removed": worst_result.functions_removed,
                    "functions_added": worst_result.functions_added,
                    "_result": worst_result,
                    "_lib_results": lib_results,  # per-library breakdown
                })

    # ── Output ────────────────────────────────────────────────────────────────
    import datetime as _dt
    import re as _re2
    total = len([r for r in rows if r[3] is not None])
    ok    = len([r for r in rows if r[4] is True])
    _generated_at = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Always build the full JSON dict (used by json / report-dir paths)
    _json_channel, _json_pkg = _parse_spec_parts(spec)
    _json_dict = {
        "spec": str(spec),
        "channel": _json_channel,
        "package": _json_pkg,
        "source_url": _apt_index_url,
        "library": library_name or "(auto-detect)",
        "generated_at": _generated_at,
        "total_transitions": total,
        "compliant": ok,
        "violations": len(violations),
        "strict": args.strict,
        "violation_details": [
            {
                "from": e["from"], "to": e["to"], "kind": e["kind"],
                "exit_code": e["exit_code"], "verdict": e["verdict"],
                "functions_removed": e["functions_removed"],
                "functions_added": e["functions_added"],
                "symbols_by_tier": {
                    "removed": e["_result"].group_by_tier_and_ns(e["_result"].public_removed) if e.get("_result") else {},
                    "added":   e["_result"].group_by_tier_and_ns(e["_result"].public_added)   if e.get("_result") else {},
                    "changed": e["_result"].group_by_tier_and_ns(e["_result"].public_changed) if e.get("_result") else {},
                },
                "symbols_removed": e["_result"].public_removed if e.get("_result") else [],
                "symbols_added":   e["_result"].public_added   if e.get("_result") else [],
                "symbols_changed": e["_result"].public_changed if e.get("_result") else [],
            }
            for e in violations
        ],
        "rows": [
            {
                "from": old_v, "to": new_v, "kind": kind,
                "exit_code": r.exit_code if r else None,
                "verdict": VERDICT.get(r.exit_code, f"rc={r.exit_code}") if r else "SKIPPED",
                "compliant": c,
                "tool": "nm-D" if r and "[nm-D fallback" in (r.stdout or "") else ("abidiff" if r else None),
                "symbols_by_tier": {
                    "removed": r.group_by_tier_and_ns(r.public_removed) if r else {},
                    "added":   r.group_by_tier_and_ns(r.public_added)   if r else {},
                    "changed": r.group_by_tier_and_ns(r.public_changed) if r else {},
                },
                "symbols_removed": r.public_removed if r else [],
                "symbols_added":   r.public_added   if r else [],
                "symbols_changed": r.public_changed if r else [],
            }
            for old_v, new_v, kind, r, c in rows
        ],
        "skipped": skipped,
    }

    def _write_report_dir(report_dir: str) -> None:
        """Write both .json and .md into report_dir."""
        _Path = Path(report_dir)
        _Path.mkdir(parents=True, exist_ok=True)
        slug = _re2.sub(r"[^\w.-]", "_", f"{spec}_{library_name or 'auto'}_{_generated_at[:10]}")
        json_path = _Path / f"{slug}.json"
        md_path   = _Path / f"{slug}.md"
        json_path.write_text(json.dumps(_json_dict, indent=2), encoding="utf-8")
        md_path.write_text(_render_markdown_report(
            spec=str(spec),
            library_name=library_name,
            rows=rows,
            violations=violations,
            skipped=skipped,
            strict=args.strict,
            details_limit=args.details_limit,
            generated_at=_generated_at,
            VERDICT=VERDICT,
            ICON=ICON,
            source_url=_apt_index_url,
        ), encoding="utf-8")
        print("Reports saved:", file=sys.stderr)
        print(f"  Markdown: {md_path}", file=sys.stderr)
        print(f"  JSON:     {json_path}", file=sys.stderr)

    # ── Route output ──────────────────────────────────────────────────────────
    if getattr(args, "report_dir", None):
        _write_report_dir(args.report_dir)

    elif args.format == "json":
        _txt = json.dumps(_json_dict, indent=2)
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as _fh:
                _fh.write(_txt)
            print(f"Report written to {args.output}", file=sys.stderr)
        else:
            print(_txt)

    elif args.format == "markdown":
        _md = _render_markdown_report(
            spec=str(spec),
            library_name=library_name,
            rows=rows,
            violations=violations,
            skipped=skipped,
            strict=args.strict,
            details_limit=args.details_limit,
            generated_at=_generated_at,
            VERDICT=VERDICT,
            ICON=ICON,
                    source_url=_apt_index_url,
        )
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as _fh:
                _fh.write(_md)
            print(f"Report written to {args.output}", file=sys.stderr)
        else:
            print(_md)

    else:  # text
        import io as _io
        _tbuf = _io.StringIO()

        def _p(s: str = "") -> None:
            _tbuf.write(s + "\n")

        mode = "strict" if args.strict else "lenient"
        lib_label = f" ({library_name})" if library_name else ""
        _p(f"SemVer compliance report — {spec}{lib_label}  [{mode} mode]")
        _p(f"{'From':<22} {'To':<22} {'Type':<8} {'Status'}")
        _p("-" * 75)
        _skip_reasons = {(sk["from"], sk["to"]): sk.get("reason", "Download failed or library not found")
                         for sk in skipped}
        for old_v, new_v, kind, result, compliant in rows:
            if result is None:
                reason = _skip_reasons.get((old_v, new_v), "unknown")
                line = f"  ⚠️  COMPARE_FAILED ({reason})"
            else:
                icon    = ICON.get(result.verdict.value, "?")
                verdict = result.verdict.name
                flag    = "" if compliant else "  ← VIOLATION"
                stats   = f"  (-{result.functions_removed} +{result.functions_added})" \
                          if (result.functions_removed or result.functions_added) else ""
                tool    = "[nm-D]" if "[nm-D fallback" in (result.stdout or "") else "[abidiff]"
                line    = f"  {icon} {kind:<8} {verdict}{stats}  {tool}{flag}"
            _p(f"  {old_v:<22}{new_v:<22}{line}")
        _p()
        pct = int(100 * ok / total) if total else 0
        _p(f"SemVer compliance: {pct}% ({ok}/{total} transitions)")
        if violations:
            _p(f"Violations ({len(violations)}):")
            for v in violations:
                _p(f"  ❌ {v['from']} → {v['to']}  [{v['kind'].upper()}]"
                   f"  {v['verdict']}  (-{v['functions_removed']} +{v['functions_added']})")
                if v.get("_result"):
                    det = v["_result"].format_details(max_per_ns=args.details_limit)
                    if det:
                        for dline in det.splitlines():
                            _p(f"    {dline}")
        elif total == 0:
            _p("⚠️  All transitions skipped — check package name, library name, and channel config.")
        else:
            _p("No violations found. ✅")

        _text_out = _tbuf.getvalue()
        if getattr(args, "output", None):
            with open(args.output, "w", encoding="utf-8") as _fh:
                _fh.write(_text_out)
            print(f"Report written to {args.output}", file=sys.stderr)
        else:
            print(_text_out, end="")

    if skipped:
        _use_stderr = (args.format in ("json", "markdown")
                       or getattr(args, "report_dir", None)
                       or getattr(args, "output", None))
        out_stream = sys.stderr if _use_stderr else sys.stdout
        print(f"\nWarning: {len(skipped)} transition(s) skipped:", file=out_stream)
        for sk in skipped:
            reason = sk.get("reason", "Download failed or library not found")
            print(f"  ⚠️  {sk['from']} -> {sk['to']}  [{sk['kind'].upper()}]  — {reason}", file=out_stream)
        if args.fail_on != "none":
            print("  Note: skipped transitions are NOT counted as violations.", file=sys.stderr)

    if violations and args.fail_on != "none":
        return min(len(violations), 125)
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
            _apt_index_url = getattr(args, "apt_index_url", None)
            if not args.apt_pkg_pattern:
                if _apt_index_url:
                    # With a custom index URL, default to exact package name match
                    args.apt_pkg_pattern = f"^{_re.escape(spec.package)}$"
                else:
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
            entries = [(v, f) for v, f, _pkg in source.list_versions(
                args.apt_pkg_pattern, index_url=_apt_index_url)]

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
    cp.add_argument("--suppress-stdlib", action="store_true",
                     help="Filter out C++ stdlib/LLVM/fmt/spdlog internal symbols (leaked template instantiations). Reduces noise in compiler/loader libraries.")
    cp.add_argument("--apt-index-url", metavar="URL",
                    help="Custom APT Packages.gz URL for apt channel packages.")
    cp.add_argument("-v", "--verbose", action="store_true")

    # compatible
    compat = subparsers.add_parser("compatible",
        help="Find all versions ABI-compatible with a given base version")
    compat.add_argument("spec", help="Base package spec (channel:package=version)")
    compat.add_argument("--format", choices=["text", "json"], default="text")
    compat.add_argument("--library-name", help="Target .so filename (e.g. libsycl.so)")
    compat.add_argument("--suppressions", help="Path to abidiff suppressions file")
    compat.add_argument("--suppress-stdlib", action="store_true",
                     help="Filter out C++ stdlib/LLVM/fmt/spdlog internal symbols (leaked template instantiations). Reduces noise in compiler/loader libraries.")
    compat.add_argument("--filter", help="Regex filter on candidate version strings")
    compat.add_argument("--apt-pkg-pattern",
                        help="Regex for APT package names (required for apt channel)")
    compat.add_argument("--apt-index-url", metavar="URL",
                        help="Custom APT Packages.gz URL (e.g. Intel GPU driver repo). "
                             "Overrides the default Intel oneAPI index for apt channel.")
    compat.add_argument("--stop-at-first-break", action="store_true",
                        help="Stop checking as soon as first incompatible version is found")
    compat.add_argument("--fail-on", choices=["breaking", "any", "none"], default="none",
                        help="Return non-zero exit if incompatible version found")
    compat.add_argument("-v", "--verbose", action="store_true")

    # validate
    val = subparsers.add_parser("validate",
        help="Validate SemVer compliance over a range of consecutive versions")
    val.add_argument("spec", help="Package spec: channel:package (e.g. intel:oneccl-cpu)")
    val.add_argument("--format", choices=["text", "json", "markdown"], default="text",
                     help="Output format (default: text; use markdown for a human-readable report)")
    val.add_argument("--output", metavar="FILE",
                     help="Write report to FILE instead of stdout (used with --format markdown or json)")
    val.add_argument("--report-dir", metavar="DIR",
                     help="Write BOTH .md and .json reports to DIR (overrides --format/--output)")
    val.add_argument("--library-name", help="Target .so filename (e.g. libccl.so)")
    val.add_argument("--suppressions", help="Path to abidiff suppressions file")
    val.add_argument("--suppress-stdlib", action="store_true",
                     help="Filter out C++ stdlib/LLVM/fmt/spdlog internal symbols (leaked template instantiations). Reduces noise in compiler/loader libraries.")
    val.add_argument("--filter", help="Regex filter on version list (e.g. ^2021.14)")
    val.add_argument("--from-version", help="Start of version range (inclusive)")
    val.add_argument("--to-version",   help="End of version range (inclusive)")
    val.add_argument("--apt-pkg-pattern",
                     help="Regex for APT package names (required for apt channel)")
    val.add_argument("--apt-index-url", metavar="URL",
                     help="Custom APT Packages.gz URL (e.g. Intel GPU driver repo). "
                          "Overrides the default Intel oneAPI index for apt channel.")
    val.add_argument("--strict", action="store_true",
                     help="Patch releases must be NO_CHANGE (exit 0); default allows COMPATIBLE (exit 4)")
    val.add_argument("--fail-on", choices=["violations", "none"], default="none",
                     help="Return non-zero exit code based on violation count (capped at 125)")
    val.add_argument("--details-limit", type=int, default=20,
                     help="Max symbols per namespace shown per violation (default: 20, 0 = unlimited)")
    val.add_argument("-v", "--verbose", action="store_true")

    # list
    lst = subparsers.add_parser("list", help="List available versions for a package")
    lst.add_argument("spec", help="Package spec: channel:package (e.g. intel:oneccl-cpu)")
    lst.add_argument("--format", choices=["text", "json"], default="text")
    lst.add_argument("--filter", help="Regex to filter version list (e.g. ^2021.14)")
    lst.add_argument("--apt-pkg-pattern",
                     help="Regex for APT package names (required for apt channel)")
    lst.add_argument("--apt-index-url", metavar="URL",
                     help="Custom APT Packages.gz URL (e.g. Intel GPU driver repo). "
                          "Overrides the default Intel oneAPI index for apt channel.")

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
