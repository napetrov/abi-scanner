# ABI Scanner

Automated ABI (Application Binary Interface) compatibility tracking for C/C++ libraries.

**Prevents binary compatibility breaks before they reach users.**

## What is this?

ABI Scanner detects when library updates break binary compatibility (ABI), helping
maintainers validate Semantic Versioning compliance and prevent user-facing breakage.

```bash
# Find all versions ABI-compatible with a baseline
$ abi-scanner compatible intel:oneccl-cpu=2021.14.0 --library-name libccl.so

ABI compatibility report for intel:oneccl-cpu=2021.14.0
Version              Status
--------------------------------------------------
  2021.14.0          (base)
  2021.14.1          ✅ NO_CHANGE
  2021.15.0          ❌ BREAKING  (-2 +20 ~0)
  2021.15.1          ❌ BREAKING  (-2 +20 ~0)

Compatible range : 2021.14.0 - 2021.14.1
First incompatible: 2021.15.0
```

## Documentation

- **[GOALS.md](GOALS.md)** — Architecture, roadmap, success criteria
- **[QUICKSTART.md](QUICKSTART.md)** — Working examples for all commands
- **[docs/INSTALLATION.md](docs/INSTALLATION.md)** — Installation guide

## Prerequisites

| Tool | Required for | Install |
|------|-------------|---------|
| `abigail-tools` | All modes | `sudo apt install abigail-tools` |
| `gcc` | ABICC+headers mode | `sudo apt install gcc` |
| `abi-compliance-checker` | ABICC modes | `sudo apt install abi-compliance-checker` |
| `micromamba` | `intel:` and `conda-forge:` channels only | see [Installation](docs/INSTALLATION.md) |
| `dpkg-deb` | `apt:` channel | pre-installed on Debian/Ubuntu |

## Quick Start

```bash
# Prerequisites
sudo apt install abigail-tools
# micromamba is only needed for intel: and conda-forge: channels
# For apt: and local: channels, skip micromamba
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
export MAMBA_ROOT_PREFIX=$(pwd)/workspace/micromamba_root

# Install
git clone https://github.com/napetrov/abi-scanner.git
cd abi-scanner
pip install -e .

# Compare two versions (Intel conda)
abi-scanner compare intel:oneccl-cpu=2021.14.0 intel:oneccl-cpu=2021.14.1 \
  --library-name libccl.so

# Compare via APT
abi-scanner compare \
  "apt:intel-oneapi-compiler-dpcpp-cpp-runtime-2025.0=2025.0.0-1169" \
  "apt:intel-oneapi-compiler-dpcpp-cpp-runtime-2025.0=2025.0.1-1240" \
  --library-name libsycl.so

# List available versions
abi-scanner list intel:oneccl-cpu --filter '^2021\.14'

# Find compatible version range
abi-scanner compatible intel:oneccl-cpu=2021.14.0 --library-name libccl.so
```

## Current Status

| Command | Status | Supported channels |
|---------|--------|--------------------|
| `compare` | ✅ Working | intel, conda-forge, apt, local |
| `list` | ✅ Working | intel, conda-forge, apt |
| `compatible` | ✅ Working | intel, conda-forge, apt |
| `validate` | 🔲 Planned | — |

### Known ABI Results

| Library | Transition | Result |
|---------|-----------|--------|
| `libccl.so` (oneCCL) | 2021.14.0 → 2021.14.1 | ✅ NO_CHANGE |
| `libccl.so` (oneCCL) | 2021.14.x → 2021.15.0 | ❌ BREAKING (-2 +20) |
| `libsycl.so` (DPC++) | 2025.0.x patch series | ✅ Stable |
| `libsycl.so` (DPC++) | 2025.0.4 → 2025.1.0 | ❌ BREAKING (-1 +78) |
| `libsycl.so` (DPC++) | 2025.1.x → 2025.2.0 | ❌ BREAKING (-7 +94) |
| `libsycl.so` (DPC++) | 2025.2.x → 2025.3.0 | ✅ COMPATIBLE (+164) |

## Repository Structure

```
abi-scanner/
├── abi_scanner/              # Python package
│   ├── cli.py                # CLI: compare, list, compatible, validate
│   ├── package_spec.py       # Spec parser: channel:package=version
│   ├── analyzer.py           # ABIAnalyzer, PublicAPIFilter
│   └── sources/              # Source adapters
│       ├── conda.py          # micromamba (conda-forge, intel)
│       ├── apt.py            # Intel APT + resolve_url/list_versions
│       ├── local.py          # Local .so/.deb/archives
│       └── factory.py        # Adapter factory + micromamba auto-detect
├── scripts/
│   └── compare_all_history.py  # Batch history comparison (conda + APT)
├── config/
│   ├── suppressions/
│   │   ├── onedal.txt
│   │   ├── oneccl.txt        # oneCCL internal symbol suppressions
│   │   └── compiler.txt      # DPC++ compiler suppressions
│   └── package_configs/
│       ├── oneccl.yaml       # oneCCL package metadata
│       └── compiler.yaml     # DPC++ compiler metadata
└── docs/
```

## Package Spec Format

All `abi-scanner` commands accept packages in `channel:package=version` format:

```
channel:package=version
```

**Channels:**

| Channel | Description | Example |
|---------|-------------|---------|
| `apt:` | Intel oneAPI APT repository | `apt:intel-oneapi-dnnl=2025.2.0` |
| `intel:` | Intel conda channel (requires micromamba) | `intel:oneccl-cpu=2021.14.0` |
| `conda-forge:` | conda-forge channel (requires micromamba) | `conda-forge:dal=2025.9.0` |
| `local:` | Local file (`.so`, `.deb`, directory) | `local:/path/to/libfoo.so` |
| `dump:` | Pre-saved abidw XML baseline | `dump:~/.abi-snapshots/libfoo.so-2025.2.abi` |

For `list` and `compatible` commands, version is optional:
```
abi-scanner list intel:oneccl-cpu
abi-scanner list apt:intel-oneapi-dnnl --apt-index-url <url>
```

## Exit Codes

| Code | Meaning | Safe for |
|------|---------|---------|
| 0 | No ABI changes | patch, minor, major |
| 4 | Additions only (compatible) | minor, major |
| 8 | Incompatible changes | major only |
| 12 | Breaking + additions | major only |


## ABICC Integration (Type-Level ABI Analysis)

Use `--abicc` to run `abi-compliance-checker` alongside abidiff for type-level ABI checking:

```bash
python scripts/compare_all_history.py --config config/package_configs/dnnl.yaml --source apt --abicc
```

Combined verdict statuses:
- ✅ `NO_CHANGE` — no symbols changed (exact same)
- ✅ `COMPATIBLE` — only additive changes (new symbols), backward-compatible
- ⚠️ `ELF_INTERNAL` — abidiff found symbol changes, ABICC confirms no type-level break (likely internal symbols, not public API)
- 🟠 `SOURCE_BREAK` — ABICC found source-level incompatibility not caught by abidiff
- 🔴 `BINARY_BREAK` — ABICC found binary-level break (vtable, layout) not caught by abidiff
- 🔴 `BREAKING` — breaking change confirmed by both tools

Requires: `apt install abi-compliance-checker`  
Products with ABICC enabled: `dnnl`, `mkl`, `tbb`, `level_zero`  
Products without ABICC (SYCL API): `onedal`, `oneccl`, `compiler`, `igc`

## License

MIT License — see LICENSE file.

## Contact

- **Maintainer:** Nikolay Petrov (Intel)
- **Issues:** [GitHub Issues](https://github.com/napetrov/abi-scanner/issues)
- **Related:** [libabigail](https://sourceware.org/libabigail/)

---
**Status:** Active Development | v0.2.0-dev

## Local Build Comparison & CI Integration

Compare your local builds against published releases, or use pre-saved ABI snapshots
for fast offline CI — no re-downloading on every PR.


```bash
# One-off: compare local .deb vs published release
abi-scanner compare \
  apt:intel-oneapi-dnnl=2025.2.0 \
  local:/path/to/my-build.deb \
  --library-name libdnnl.so \
  --apt-index-url https://apt.repos.intel.com/oneapi/dists/all/main/binary-amd64/Packages.gz \
  --fail-on breaking

# Snapshot a baseline for offline use
abi-scanner snapshot apt:intel-oneapi-dnnl=2025.2.0 \
  --output-dir ~/.abi-snapshots/dnnl

# Compare against snapshot (no download, no network)
abi-scanner compare \
  dump:~/.abi-snapshots/dnnl/libdnnl.so-2025.2.0.abi \
  local:/path/to/my-build/libdnnl.so \
  --fail-on breaking
```

**→ See [docs/local_compare.md](docs/local_compare.md) for the full guide**, including:
- CI integration patterns (nightly snapshot + PR compare)
- Multi-library snapshots
- Manifest format
- Air-gapped / artifact registry workflows
