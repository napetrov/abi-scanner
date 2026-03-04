#!/usr/bin/env python3
"""Generate per-product ABI compatibility reports from per-library JSON scan results."""
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from packaging.version import Version, InvalidVersion

sys.path.insert(0, str(Path(__file__).parent.parent))
from abi_scanner.sources.apt import normalize_debian_version

CHANNEL_URL = "https://apt.repos.intel.com/oneapi"
MAX_SYMBOLS_MD = 10

PRODUCT_PKG_MAP = {
    "onedal": "intel-oneapi-dal",
    "oneccl": "intel-oneapi-ccl",
    "compiler": "intel-oneapi-compiler-dpcpp-cpp-runtime",
    "mkl": "intel-oneapi-mkl-core",
}

PRODUCT_DISPLAY = {
    "onedal": "Intel oneDAL",
    "oneccl": "Intel oneCCL",
    "compiler": "Intel DPC++ Compiler Runtime",
    "mkl": "Intel MKL",
    "dnnl": "Intel oneDNN",
    "igc": "Intel Graphics Compiler (IGC)",
    "level_zero": "Intel Level Zero",
    "tbb": "Intel oneTBB",
}

LEGEND = """\
## Legend

| Status | Meaning |
|---|---|
| ✅ NO_CHANGE | Identical ABI — no differences detected |
| ℹ️ COMPATIBLE | ABI changed, but backward-compatible (e.g. new functions added; existing callers unaffected) |
| ❌ BREAKING | Incompatible ABI change — binaries compiled against the old version may fail to link or crash at runtime |
| 🆕 NEW | Library first appeared in this release (not present in earlier versions) |

**Table columns (BREAKING rows):**
- **Removed** — functions/symbols removed; existing callers of these will get link errors
- **Changed** — functions whose signature changed; callers compiled against old headers may behave incorrectly
- **Added** — new functions; backward-compatible on its own
- **ELF-only** — symbols present in the binary's ELF table but without debug info (e.g. compiler internals, dispatch stubs); removal is still a linker-visible ABI break

> All counts come directly from `abidiff` output. If a column shows `—` it means zero changes of that kind.
"""


def ver_key(v: str):
    try:
        return Version(normalize_debian_version(v))
    except InvalidVersion:
        return Version("0")


def strip_build(v: str) -> str:
    return v.split("-")[0]


def get_status_emoji(status: str) -> str:
    return {"NO_CHANGE": "✅ NO_CHANGE", "COMPATIBLE": "ℹ️ COMPATIBLE",
            "BREAKING": "❌ BREAKING"}.get(status, f"❓ {status}")


def parse_summary(s: str) -> dict:
    r = dict(fn_rm=0, fn_ch=0, fn_add=0, var_rm=0, var_ch=0, var_add=0,
             elf_fn_rm=0, elf_fn_add=0, elf_var_rm=0, elf_var_add=0)
    for line in s.splitlines():
        line = line.strip()
        m = re.search(r"Functions changes summary: (\d+) Removed, (\d+) Changed.*?(\d+) Added", line)
        if m:
            r["fn_rm"], r["fn_ch"], r["fn_add"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
        m = re.search(r"Variables changes summary: (\d+) Removed, (\d+) Changed.*?(\d+) Added", line)
        if m:
            r["var_rm"], r["var_ch"], r["var_add"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
        m = re.search(r"Function symbols changes summary: (\d+) Removed, (\d+) Added", line)
        if m:
            r["elf_fn_rm"], r["elf_fn_add"] = int(m.group(1)), int(m.group(2))
        m = re.search(r"Variable symbols changes summary: (\d+) Removed, (\d+) Added", line)
        if m:
            r["elf_var_rm"], r["elf_var_add"] = int(m.group(1)), int(m.group(2))
    return r


def fmt(n: int) -> str:
    return str(n) if n > 0 else "—"


def load_library_jsons(product: str, abi_dir: Path) -> dict:
    apt_dir = abi_dir / product / "apt"
    results = {}
    if not apt_dir.exists():
        return results
    for f in sorted(apt_dir.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
        lib_name = f.stem.replace("_so_", ".so.").replace("_so", ".so")
        results[lib_name] = data
    return results


def generate_product_report(product: str, lib_data: dict, scan_date: str, reports_dir: Path):
    pkg_name = PRODUCT_PKG_MAP.get(product, f"intel-oneapi-{product}")
    display_name = PRODUCT_DISPLAY.get(product, product.upper())
    libraries_scanned = sorted(lib_data.keys())

    all_pairs: set = set()
    by_version: dict = defaultdict(list)
    headers_used = None
    runtime_pkgs: set = set()
    devel_patterns: set = set()

    for lib_name, data in lib_data.items():
        if data.get("package"):
            runtime_pkgs.add(data["package"])
        if data.get("devel_pkg_pattern"):
            devel_patterns.add(data["devel_pkg_pattern"])
        for comp in data.get("comparisons", []):
            old_v = comp.get("old_version", "?")
            new_v = comp.get("new_version", "?")
            pair = (old_v, new_v)
            all_pairs.add(pair)
            if headers_used is None:
                headers_used = comp.get("headers_used", False)
            by_version[pair].append({
                "library":   lib_name,
                "status":    comp.get("status", "UNKNOWN"),
                "summary":   comp.get("abidiff_summary", ""),
                "removed":   comp.get("symbols", {}).get("public", {}).get("removed", []),
                "added":     comp.get("symbols", {}).get("public", {}).get("added", []),
                "type_ch":   comp.get("type_changes_count", 0),
            })

    sorted_pairs = sorted(all_pairs, key=lambda p: (ver_key(p[0]), ver_key(p[1])))
    first_pair = sorted_pairs[0] if sorted_pairs else None
    libs_in_first = {r["library"] for r in by_version.get(first_pair, [])} if first_pair else set()
    first_seen: dict = {}
    for pair in sorted_pairs:
        for r in by_version[pair]:
            first_seen.setdefault(r["library"], pair)

    def is_new(lib, pair):
        return lib not in libs_in_first and first_seen.get(lib) == pair

    # JSON
    json_results = []
    for pair in sorted_pairs:
        for r in by_version[pair]:
            s = parse_summary(r["summary"])
            if str(r.get("status","")).startswith("UNKNOWN"):
                continue
            json_results.append({
                "version_pair": f"{pair[0]} → {pair[1]}",
                "library": r["library"],
                "status": "NEW" if is_new(r["library"], pair) else r["status"],
                "fn_removed": s["fn_rm"], "fn_changed": s["fn_ch"], "fn_added": s["fn_add"],
                "elf_fn_removed": s["elf_fn_rm"], "elf_fn_added": s["elf_fn_add"],
                "elf_var_removed": s["elf_var_rm"], "elf_var_added": s["elf_var_add"],
                "removed_symbols": r["removed"], "added_symbols": r["added"],
            })

    json_out = {
        "product": product, "channel_url": CHANNEL_URL, "package": pkg_name,
        "runtime_packages": sorted(runtime_pkgs), "devel_packages": sorted(devel_patterns),
        "libraries_scanned": libraries_scanned, "headers_used": headers_used,
        "scan_date": scan_date, "results": json_results,
    }
    with open(reports_dir / f"{product}_apt_full.json", "w") as f:
        json.dump(json_out, f, indent=2)

    # MD
    md = []
    md.append(f"# {display_name} ABI Compatibility Report\n")
    md.append(f"**Channel:** {CHANNEL_URL}  ")
    md.append(f"**Package:** {pkg_name}  ")
    if runtime_pkgs:
        md.append(f"**Runtime packages:** {', '.join(sorted(runtime_pkgs))}  ")
    if devel_patterns:
        md.append(f"**Devel packages:** {', '.join(sorted(devel_patterns))}  ")
    md.append(f"**Libraries scanned:** {', '.join(libraries_scanned)}  ")
    md.append(f"**Headers used:** {'✅ Yes' if headers_used else '❌ No'}  ")
    md.append(f"**Scan date:** {scan_date}  ")
    md.append("")
    md.append(LEGEND)
    md.append("## Summary\n")

    breaking_entries = []  # (old_s, new_s, row, s_dict)

    for i, pair in enumerate(sorted_pairs):
        old_v, new_v = pair
        old_s, new_s = strip_build(old_v), strip_build(new_v)
        rows = sorted(by_version[pair], key=lambda x: x["library"])

        md.append(f"### {old_s} → {new_s}\n")
        md.append("| Library | Status | Removed | Changed | Added | ELF-only removed |")
        md.append("|---|---|---|---|---|---|")

        for r in rows:
            if str(r["status"]).startswith("UNKNOWN"):
                continue
            new_flag = is_new(r["library"], pair)
            if new_flag:
                md.append(f"| {r['library']} | 🆕 NEW | — | — | — | — |")
                continue

            s = parse_summary(r["summary"])
            elf_rm = s["elf_fn_rm"] + s["elf_var_rm"]

            # Use abidiff-summary counts for removed/changed/added (more accurate than symbol list lengths)
            total_rm  = s["fn_rm"] + s["var_rm"]
            total_ch  = s["fn_ch"] + s["var_ch"] + r["type_ch"]
            total_add = s["fn_add"] + s["var_add"]

            rm_cell  = fmt(total_rm)
            ch_cell  = fmt(total_ch)
            add_cell = fmt(total_add)
            elf_cell = fmt(elf_rm)

            md.append(f"| {r['library']} | {get_status_emoji(r['status'])} "
                      f"| {rm_cell} | {ch_cell} | {add_cell} | {elf_cell} |")

            if r["status"] == "BREAKING":
                breaking_entries.append((old_s, new_s, r, s))

        if i < len(sorted_pairs) - 1:
            md += ["", "---", ""]

    # Breaking section
    if breaking_entries:
        md += ["", "## Breaking Changes", ""]
        current = None
        for old_s, new_s, r, s in breaking_entries:
            label = f"{old_s} → {new_s}"
            if label != current:
                if current is not None:
                    md += ["---", ""]
                md += [f"### {label}", ""]
                current = label

            md += [f"#### `{r['library']}`", ""]

            # Human-readable explanation
            reasons = []
            if s["fn_rm"]:
                reasons.append(f"**{s['fn_rm']} function(s) removed** — "
                                f"any caller of these functions will fail to link")
            if s["var_rm"]:
                reasons.append(f"**{s['var_rm']} variable(s) removed**")
            if s["fn_ch"]:
                reasons.append(f"**{s['fn_ch']} function(s) changed** — "
                                f"signature/layout modified; callers compiled with old headers may misbehave")
            if s["var_ch"]:
                reasons.append(f"**{s['var_ch']} variable(s) changed** — layout modified")
            if r["type_ch"]:
                reasons.append(f"**{r['type_ch']} type(s) changed** — struct/class layout modified")
            elf_rm = s["elf_fn_rm"] + s["elf_var_rm"]
            if elf_rm:
                reasons.append(
                    f"**{elf_rm} ELF symbol(s) removed** (no debug info) — "
                    f"these symbols exist in the binary's ELF symbol table but have no DWARF entries. "
                    f"They are typically internal implementation details (compiler dispatch stubs, "
                    f"SYCL JIT entries, etc). abidiff still flags removal as BREAKING because "
                    f"any binary that linked to them directly will get an undefined symbol error."
                )
            if s["fn_add"] and not reasons:
                reasons.append(f"**{s['fn_add']} function(s) added only** — "
                                f"abidiff flagged this BREAKING, unusual; may be a false positive")

            if not reasons:
                reasons.append(
                    f"abidiff returned exit code 12 (BREAKING) but counters are all zero. "
                    f"This is rare and may indicate vtable slot reordering or a linker script change. "
                    f"See full abidiff summary below."
                )

            md.append("**Why BREAKING:**")
            for reason in reasons:
                md.append(f"- {reason}")
            md.append("")

            if r["summary"]:
                md += ["<details><summary>Full abidiff output</summary>", "",
                       "```", r["summary"].strip(), "```", "</details>", ""]

            if r["removed"]:
                shown = r["removed"][:MAX_SYMBOLS_MD]
                extra = len(r["removed"]) - len(shown)
                md += [f"**Removed symbols ({len(r['removed'])}):**", "```cpp"] + shown + ["```"]
                if extra:
                    md.append(f"*...and {extra} more — see JSON*")
                md.append("")

            if r["added"]:
                shown = r["added"][:MAX_SYMBOLS_MD]
                extra = len(r["added"]) - len(shown)
                md += [f"**Added symbols ({len(r['added'])}):**", "```cpp"] + shown + ["```"]
                if extra:
                    md.append(f"*...and {extra} more — see JSON*")
                md.append("")

    with open(reports_dir / f"{product}_apt.md", "w") as f:
        f.write("\n".join(md) + "\n")


def main():
    repo_root = Path(__file__).parent.parent
    abi_dir = repo_root / "abi_reports"
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    scan_date = date.today().isoformat()
    products = [d.name for d in sorted(abi_dir.iterdir())
                if d.is_dir() and (abi_dir / d.name / "apt").exists()]
    if not products:
        print("No scan results found in abi_reports/*/apt/")
        sys.exit(1)
    for product in products:
        print(f"Processing {product}...")
        lib_data = load_library_jsons(product, abi_dir)
        if lib_data:
            generate_product_report(product, lib_data, scan_date, reports_dir)


if __name__ == "__main__":
    main()
