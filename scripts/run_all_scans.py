#!/usr/bin/env python3
"""Config-driven ABI scanner runner.

Reads package configs from config/package_configs/*.yaml and runs
compare_all_history.py for each product, channel, and library.

Auto-discovery: downloads one version of each package, finds ALL .so files,
warns about any .so not listed in config. Use --discover-all to scan them too.
"""
import argparse, subprocess, sys, shutil, tempfile, gzip, re, urllib.request
from pathlib import Path
import yaml, json


def load_configs(config_dir: Path):
    configs = {}
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            config = yaml.safe_load(f)
            configs[config['library']] = config
    return configs


def find_micromamba():
    for c in [shutil.which('micromamba'), '/home/ubuntu/bin/micromamba', '/usr/local/bin/micromamba']:
        if c and Path(c).exists():
            return c
    return None


def _base_so(name):
    """libfoo.so.1.0 -> libfoo.so"""
    return name.split('.so')[0] + '.so'


def discover_conda_libs(channel, package, verbose=False):
    """Install latest package version; return all real .so filenames found."""
    mamba = find_micromamba()
    if not mamba:
        print("  [discover] micromamba not found")
        return []
    with tempfile.TemporaryDirectory(prefix='abi_disc_') as tmp:
        r = subprocess.run([mamba, 'create', '-p', tmp, '--channel', channel,
                            package, '-y', '--no-deps'], capture_output=not verbose)
        if r.returncode != 0:
            print(f"  [discover] install failed for {package}")
            return []
        return sorted({p.name for p in Path(tmp).rglob('*.so*')
                       if not p.is_symlink() and '.so' in p.name})


def discover_apt_libs(pkg_pattern, verbose=False):
    """Fetch Intel APT index, download one .deb, return all real .so filenames."""
    APT_INDEX = 'https://apt.repos.intel.com/oneapi/dists/all/main/binary-amd64/Packages.gz'
    try:
        data = gzip.decompress(urllib.request.urlopen(APT_INDEX, timeout=30).read()).decode('utf-8', 'ignore')
    except Exception as e:
        print(f"  [discover] APT index fetch failed: {e}")
        return []
    pat = re.compile(pkg_pattern)
    filenames = []
    for block in data.split('\n\n'):
        nm = re.search(r'^Package: (.+)$', block, re.M)
        fn = re.search(r'^Filename: (.+)$', block, re.M)
        if nm and fn and pat.match(nm.group(1).strip()):
            filenames.append(fn.group(1).strip())
    if not filenames:
        print(f"  [discover] no APT packages matched '{pkg_pattern}'")
        return []
    deb_url = 'https://apt.repos.intel.com/oneapi/' + filenames[-1]
    if verbose:
        print(f"  [discover] downloading {deb_url}")
    with tempfile.TemporaryDirectory(prefix='abi_apt_disc_') as tmp:
        deb = f"{tmp}/pkg.deb"
        try:
            urllib.request.urlretrieve(deb_url, deb)
            subprocess.run(['dpkg', '-x', deb, tmp], check=True, capture_output=True)
        except Exception as e:
            print(f"  [discover] APT extract failed: {e}")
            return []
        return sorted({p.name for p in Path(tmp).rglob('*.so*')
                       if not p.is_symlink() and '.so' in p.name})


def check_coverage(product, source_name, source_config, channel, package, config_libs, verbose):
    """Find .so files in package not covered by config. Returns list of uncovered base names."""
    print(f"\n[discover] {product}/{source_name}: inspecting package '{package}'")

    if source_name == 'apt':
        pkg_pat = source_config.get('pkg_pattern')
        if not pkg_pat:
            print("  [discover] no pkg_pattern in config — skipping")
            return []
        found_raw = discover_apt_libs(pkg_pat, verbose=verbose)
    elif 'channel' in source_config:
        found_raw = discover_conda_libs(channel, package, verbose=verbose)
    else:
        print("  [discover] unknown source type — skipping")
        return []

    if not found_raw:
        return []

    config_bases = {_base_so(l) for l in config_libs}
    found_bases  = {_base_so(l) for l in found_raw}
    uncovered = sorted(found_bases - config_bases)

    if uncovered:
        print(f"  ⚠️  UNCOVERED .so (in package, NOT in config) — add to libraries[] or use --discover-all:")
        for lib in uncovered:
            print(f"       {lib}")
    else:
        print(f"  ✅ Config covers all {len(found_bases)} .so files in package")
    return uncovered


def run_scan(product, channel, package, library, args, apt_pkg_pattern=None, apt_packages_url=None, apt_base_url=None):
    """Run compare_all_history.py for one library."""
    safe_ch = re.sub(r'[/:.]', '_', channel)
    out_dir = args.output_dir / product / safe_ch
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_lib = re.sub(r'[/.]', '_', library).strip('_')
    json_out = out_dir / f"{safe_lib}.json"

    cmd = [sys.executable, "scripts/compare_all_history.py",
           channel, package,
           "--library-name", library,
           "--cache-dir", str(args.cache_dir),
           "--details", "--details-limit", "10",
           "--json", str(json_out)]
    if apt_pkg_pattern:
        cmd += ["--apt-pkg-pattern", apt_pkg_pattern]
    if apt_packages_url:
        cmd += ["--apt-packages-url", apt_packages_url]
    if apt_base_url:
        cmd += ["--apt-base-url", apt_base_url]
    if args.filter_version:
        cmd += ["--filter-version", args.filter_version]
    if args.track_preview:
        cmd.append("--track-preview")
    if args.verbose:
        cmd.append("--verbose")

    print(f"\n{'='*80}")
    print(f"Scanning: {product} / {channel} / {library}")
    print(f"{'='*80}\n")

    result = subprocess.run(cmd, capture_output=not args.verbose)
    if not args.verbose and result.stdout:
        print(result.stdout.decode())
    if result.returncode == 1:
        if not args.verbose and result.stderr:
            print(result.stderr.decode())
        return {"product": product, "channel": channel, "library": library,
                "status": "error", "error": "no versions / bad args"}
    status_map = {0: "no_change", 4: "compatible", 8: "incompatible", 12: "breaking"}
    status = status_map.get(result.returncode, f"exit_{result.returncode}")
    return {"product": product, "channel": channel, "library": library,
            "status": status, "output": str(json_out)}


def main():
    p = argparse.ArgumentParser(description="Config-driven ABI scan runner")
    p.add_argument("--config-dir",      type=Path, default=Path("config/package_configs"))
    p.add_argument("--output-dir",      type=Path, default=Path("abi_reports"))
    p.add_argument("--cache-dir",       type=Path, default=Path("workspace"))
    p.add_argument("--products",        nargs="+", help="Filter products (e.g. onedal oneccl)")
    p.add_argument("--channels",        nargs="+", help="Filter source names (e.g. intel apt)")
    p.add_argument("--filter-version",  help="Version regex (e.g. ^2025)")
    p.add_argument("--track-preview",   action="store_true")
    p.add_argument("--verbose",         action="store_true")
    p.add_argument("--discover",        action="store_true",
                   help="Check package for .so not in config (warns, does not scan)")
    p.add_argument("--discover-all",    action="store_true",
                   help="Like --discover but also scans uncovered libs")
    args = p.parse_args()

    configs = load_configs(args.config_dir)
    print(f"Loaded configs: {', '.join(configs.keys())}")
    if args.products:
        configs = {k: v for k, v in configs.items() if k in args.products}
        print(f"Filtered to: {', '.join(configs.keys())}")

    results = []
    for product, config in configs.items():
        config_libs = config.get('libraries', [config['primary_lib']])
        for source_name, source_config in config['sources'].items():
            if args.channels and source_name not in args.channels:
                continue
            if source_name == 'apt':
                channel, package = 'apt', product
            elif 'channel' in source_config:
                channel = source_config['channel']
                package = source_config.get('package', product)
            else:
                print(f"Skipping {product}/{source_name}: no channel info")
                continue

            extra_libs = []
            if args.discover or args.discover_all:
                uncovered = check_coverage(product, source_name, source_config,
                                           channel, package, config_libs, args.verbose)
                if args.discover_all:
                    extra_libs = uncovered

            for library in list(config_libs) + extra_libs:
                pkg_pat = source_config.get('pkg_pattern') if source_name == 'apt' else None
                pkg_url = source_config.get('apt_packages_url') if source_name == 'apt' else None
                base_url = source_config.get('base_url') if source_name == 'apt' else None
                results.append(run_scan(product, channel, package, library, args,
                                        apt_pkg_pattern=pkg_pat, apt_packages_url=pkg_url,
                                        apt_base_url=base_url))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = args.output_dir / "scan_summary.json"
    with open(summary, 'w') as f:
        json.dump(results, f, indent=2)

    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    icons = {'no_change': '✅', 'compatible': '✅', 'incompatible': '⚠️', 'breaking': '❌', 'error': '💥'}
    print(f"\n{'='*80}\nScan complete → {summary}")
    print(f"Total: {len(results)}")
    for s, n in sorted(counts.items()):
        print(f"  {icons.get(s,'?')} {s}: {n}")
    print('='*80)

if __name__ == "__main__":
    main()
