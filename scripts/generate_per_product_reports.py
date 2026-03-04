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
    "onedal":      "Intel oneDAL",
    "oneccl":      "Intel oneCCL",
    "compiler":    "Intel DPC++ Compiler Runtime",
    "mkl":         "Intel MKL",
    "dnnl":        "Intel oneDNN",
    "igc":         "Intel Graphics Compiler (IGC)",
    "level_zero":  "Intel Level Zero",
    "tbb":         "Intel oneTBB",
}

LEGEND = """\
## Legend

| Status      | Meaning                                                                                        |
|-------------|------------------------------------------------------------------------------------------------|
| ✅ NO_CHANGE | Identical ABI — no differences detected                                                       |
| ℹ️ COMPATIBLE | ABI changed, but backward-compatible (new symbols added; existing callers unaffected)        |
| ❌ BREAKING  | Incompatible ABI change — binaries compiled against the old version may fail to link or crash |
| 🆕 NEW       | Library first appeared in this release                                                        |

**Symbol categories:**
- **Public**   — stable, documented API; callers depend on these directly
- **Preview**  — experimental/preview API (`Exp` suffix, `preview::` namespace); may change between releases
- **Internal** — implementation details (`detail::`, `impl::`, etc.); not part of public contract, but ELF-visible

**Table columns:**
`Pub rm/add` / `Prev rm/add` / `Int rm/add` = removed/added symbols per category;
`Changed` = function signatures or type layouts changed; `ELF rm` = ELF-only removals (no DWARF info)
"""


def ver_key(v: str):
    try:
        return Version(normalize_debian_version(v))
    except InvalidVersion:
        return Version("0")


def strip_build(v: str) -> str:
    return v.split("-")[0]


def get_status_emoji(status: str) -> str:
    return {
        "NO_CHANGE":  "✅ NO_CHANGE",
        "COMPATIBLE": "ℹ️ COMPATIBLE",
        "BREAKING":   "❌ BREAKING",
    }.get(status, f"❓ {status}")


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


def make_table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Render an aligned markdown table (looks good in raw form too)."""
    all_rows = [header] + rows
    widths = [max(len(cell) for cell in col) for col in zip(*all_rows)]

    def pad_row(row, sep="|"):
        cells = [f" {cell.ljust(w)} " for cell, w in zip(row, widths)]
        return sep + sep.join(cells) + sep

    separator = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    lines = [pad_row(header), separator]
    for row in rows:
        lines.append(pad_row(row))
    return lines


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
    pkg_name      = PRODUCT_PKG_MAP.get(product, f"intel-oneapi-{product}")
    display_name  = PRODUCT_DISPLAY.get(product, product.upper())
    libraries_scanned = sorted(lib_data.keys())

    all_pairs      = set()
    by_version     = defaultdict(list)
    headers_used   = None
    runtime_pkgs   = set()
    devel_patterns = set()

    for lib_name, data in lib_data.items():
        if data.get("package"):
            runtime_pkgs.add(data["package"])
        if data.get("devel_pkg_pattern"):
            devel_patterns.add(data["devel_pkg_pattern"])
        for comp in data.get("comparisons", []):
            if str(comp.get("status", "")).startswith("UNKNOWN"):
                continue
            old_v = comp.get("old_version", "?")
            new_v = comp.get("new_version", "?")
            pair  = (old_v, new_v)
            all_pairs.add(pair)
            if headers_used is None:
                headers_used = comp.get("headers_used", False)

            syms  = comp.get("symbols", {})
            stats = comp.get("stats", {})
            by_version[pair].append({
                "library":    lib_name,
                "status":     comp.get("status", "UNKNOWN"),
                "summary":    comp.get("abidiff_summary", ""),
                "type_ch":    comp.get("type_changes_count", 0),
                # symbol lists (capped at MAX_SYMBOLS_MD for display)
                "pub_rm":     syms.get("public",   {}).get("removed", []),
                "pub_add":    syms.get("public",   {}).get("added",   []),
                "prev_rm":    syms.get("preview",  {}).get("removed", []),
                "prev_add":   syms.get("preview",  {}).get("added",   []),
                "int_rm":     syms.get("internal", {}).get("removed", []),
                "int_add":    syms.get("internal", {}).get("added",   []),
                # stats counts (scanner-filtered totals)
                "pub_rm_n":   stats.get("public",   {}).get("removed", 0),
                "pub_add_n":  stats.get("public",   {}).get("added",   0),
                "prev_rm_n":  stats.get("preview",  {}).get("removed", 0),
                "prev_add_n": stats.get("preview",  {}).get("added",   0),
                "int_rm_n":   stats.get("internal", {}).get("removed", 0),
                "int_add_n":  stats.get("internal", {}).get("added",   0),
            })

    sorted_pairs = sorted(all_pairs, key=lambda p: (ver_key(p[0]), ver_key(p[1])))
    first_pair   = sorted_pairs[0] if sorted_pairs else None
    libs_in_first = {r["library"] for r in by_version.get(first_pair, [])} if first_pair else set()
    first_seen: dict = {}
    for pair in sorted_pairs:
        for r in by_version[pair]:
            first_seen.setdefault(r["library"], pair)

    def is_new(lib, pair):
        return lib not in libs_in_first and first_seen.get(lib) == pair

    # ── JSON output ──────────────────────────────────────────────────────────
    json_results = []
    for pair in sorted_pairs:
        for r in by_version[pair]:
            if str(r["status"]).startswith("UNKNOWN"):
                continue
            s = parse_summary(r["summary"])
            new_flag = is_new(r["library"], pair)
            json_results.append({
                "version_pair": f"{pair[0]} → {pair[1]}",
                "library":      r["library"],
                "status":       "NEW" if new_flag else r["status"],
                "symbols": {
                    "public":   {"removed": r["pub_rm"],  "added": r["pub_add"]},
                    "preview":  {"removed": r["prev_rm"], "added": r["prev_add"]},
                    "internal": {"removed": r["int_rm"],  "added": r["int_add"]},
                },
                "stats": {
                    "public":   {"removed": r["pub_rm_n"],  "added": r["pub_add_n"]},
                    "preview":  {"removed": r["prev_rm_n"], "added": r["prev_add_n"]},
                    "internal": {"removed": r["int_rm_n"],  "added": r["int_add_n"]},
                },
                "fn_changed":      s["fn_ch"],
                "elf_fn_removed":  s["elf_fn_rm"],
                "elf_var_removed": s["elf_var_rm"],
            })

    json_out = {
        "product": product, "channel_url": CHANNEL_URL, "package": pkg_name,
        "runtime_packages":  sorted(runtime_pkgs),
        "devel_packages":    sorted(devel_patterns),
        "libraries_scanned": libraries_scanned,
        "headers_used": headers_used,
        "scan_date":    scan_date,
        "results":      json_results,
    }
    with open(reports_dir / f"{product}_apt_full.json", "w") as f:
        json.dump(json_out, f, indent=2)

    # ── Markdown output ───────────────────────────────────────────────────────
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

    breaking_entries = []
    TABLE_HEADER = ["Library", "Status",
                    "Pub rm", "Pub add",
                    "Prev rm", "Prev add",
                    "Int rm", "Int add",
                    "Changed", "ELF rm"]
    NEW_ROW_TEMPLATE = ["—"] * 8  # placeholder cells for non-status cols

    for i, pair in enumerate(sorted_pairs):
        old_v, new_v = pair
        rows = sorted(by_version[pair], key=lambda x: x["library"])
        md.append(f"### {strip_build(old_v)} → {strip_build(new_v)}\n")

        table_rows = []
        for r in rows:
            if str(r["status"]).startswith("UNKNOWN"):
                continue
            new_flag = is_new(r["library"], pair)
            if new_flag:
                table_rows.append([r["library"], "🆕 NEW"] + NEW_ROW_TEMPLATE)
                continue

            s = parse_summary(r["summary"])
            elf_rm   = s["elf_fn_rm"] + s["elf_var_rm"]
            total_ch = s["fn_ch"] + s["var_ch"] + r["type_ch"]

            # Counts: prefer stats, fall back to list length
            pub_rm  = r["pub_rm_n"]  or len(r["pub_rm"])
            pub_add = r["pub_add_n"] or len(r["pub_add"])
            prev_rm = r["prev_rm_n"] or len(r["prev_rm"])
            prev_add= r["prev_add_n"]or len(r["prev_add"])
            int_rm  = r["int_rm_n"]  or len(r["int_rm"])
            int_add = r["int_add_n"] or len(r["int_add"])

            # Conservative: if abidiff total_rm > categorised sum, attribute to public
            abidiff_total_rm = s["fn_rm"] + s["var_rm"]
            if abidiff_total_rm > pub_rm + prev_rm + int_rm:
                pub_rm = abidiff_total_rm

            table_rows.append([
                r["library"],
                get_status_emoji(r["status"]),
                fmt(pub_rm),  fmt(pub_add),
                fmt(prev_rm), fmt(prev_add),
                fmt(int_rm),  fmt(int_add),
                fmt(total_ch),
                fmt(elf_rm),
            ])

            if r["status"] == "BREAKING":
                breaking_entries.append((strip_build(old_v), strip_build(new_v), r, s))

        md += make_table(TABLE_HEADER, table_rows)

        if i < len(sorted_pairs) - 1:
            md += ["", "---", ""]

    # ── Breaking Changes section ──────────────────────────────────────────────
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

            pub_rm  = r["pub_rm_n"]  or len(r["pub_rm"])
            pub_add = r["pub_add_n"] or len(r["pub_add"])
            prev_rm = r["prev_rm_n"] or len(r["prev_rm"])
            prev_add= r["prev_add_n"]or len(r["prev_add"])
            int_rm  = r["int_rm_n"]  or len(r["int_rm"])
            int_add = r["int_add_n"] or len(r["int_add"])
            total_ch = s["fn_ch"] + s["var_ch"] + r["type_ch"]
            elf_rm   = s["elf_fn_rm"] + s["elf_var_rm"]

            reasons = []
            if pub_rm:
                reasons.append(f"**{pub_rm} public symbol(s) removed** — callers will get link errors")
            if prev_rm:
                reasons.append(f"**{prev_rm} preview symbol(s) removed** — experimental API changed")
            if int_rm:
                reasons.append(f"**{int_rm} internal symbol(s) removed** — ELF-visible but not public contract")
            if total_ch:
                reasons.append(f"**{total_ch} function/type(s) changed** — signature or layout modified")
            if elf_rm:
                reasons.append(f"**{elf_rm} ELF-only symbol(s) removed** (no DWARF) — linker-visible ABI break")
            if not reasons:
                reasons.append("abidiff returned BREAKING (exit 12); counters are zero — "
                                "may indicate vtable or linker-script changes not captured in DWARF")

            md.append("**Why BREAKING:**")
            for reason in reasons:
                md.append(f"- {reason}")
            md.append("")

            if r.get("summary"):
                md += ["<details><summary>Full abidiff output</summary>", "",
                       "```", r["summary"].strip(), "```", "</details>", ""]

            # Per-category symbol blocks
            for cat_label, rm_list, rm_n, add_list, add_n in [
                ("🔴 Public",   r["pub_rm"],  pub_rm,  r["pub_add"],  pub_add),
                ("🟡 Preview",  r["prev_rm"], prev_rm, r["prev_add"], prev_add),
                ("⚪ Internal", r["int_rm"],  int_rm,  r["int_add"],  int_add),
            ]:
                if not rm_list and not add_list:
                    continue
                md.append(f"**{cat_label} API changes:**")
                if rm_list:
                    shown = rm_list[:MAX_SYMBOLS_MD]
                    extra = max(0, rm_n - len(shown))
                    md += [f"<details><summary>Removed ({rm_n})</summary>", "",
                           "```cpp"] + shown + ["```"]
                    if extra:
                        md.append(f"*...and {extra} more — see JSON*")
                    md += ["</details>", ""]
                if add_list:
                    shown = add_list[:MAX_SYMBOLS_MD]
                    extra = max(0, add_n - len(shown))
                    md += [f"<details><summary>Added ({add_n})</summary>", "",
                           "```cpp"] + shown + ["```"]
                    if extra:
                        md.append(f"*...and {extra} more — see JSON*")
                    md += ["</details>", ""]

    with open(reports_dir / f"{product}_apt.md", "w") as f:
        f.write("\n".join(md) + "\n")


def main():
    repo_root   = Path(__file__).parent.parent
    abi_dir     = repo_root / "abi_reports"
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
