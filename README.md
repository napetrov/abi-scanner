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

## Quick Start

```bash
# Prerequisites
sudo apt install abigail-tools
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

```
channel:package=version

intel:oneccl-cpu=2021.14.0
conda-forge:dal=2025.9.0
apt:intel-oneapi-compiler-dpcpp-cpp-runtime-2025.0=2025.0.0-1169
local:/path/to/libfoo.so

# list/compatible: version is optional
intel:oneccl-cpu
apt:compiler
```

## Exit Codes

| Code | Meaning | Safe for |
|------|---------|---------|
| 0 | No ABI changes | patch, minor, major |
| 4 | Additions only (compatible) | minor, major |
| 8 | Incompatible changes | major only |
| 12 | Breaking + additions | major only |

## License

MIT License — see LICENSE file.

## Contact

- **Maintainer:** Nikolay Petrov (Intel)
- **Issues:** [GitHub Issues](https://github.com/napetrov/abi-scanner/issues)
- **Related:** [libabigail](https://sourceware.org/libabigail/)

---
**Status:** Active Development | v0.2.0-dev
