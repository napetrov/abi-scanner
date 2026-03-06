# Installation Guide

## Prerequisites

| Tool | Required for | Install |
|------|-------------|---------|
| `abigail-tools` | All modes (abidiff + abidw) | `sudo apt install abigail-tools` |
| `python3` + `pip` | abi-scanner CLI | system python |
| `gcc` | ABICC+headers mode only | `sudo apt install gcc` |
| `abi-compliance-checker` | ABICC+headers and ABICC+dump modes | `sudo apt install abi-compliance-checker` |
| `abi-dumper`, `universal-ctags`, `vtable-dumper` | ABICC+dump mode only | `sudo apt install abi-dumper universal-ctags vtable-dumper` |
| `micromamba` | `intel:` and `conda-forge:` channels only | see below |
| `dpkg-deb` | `apt:` channel (`.deb` extraction) | usually pre-installed on Debian/Ubuntu |

> **Minimal install** (APT + local channels only): `sudo apt install abigail-tools gcc abi-compliance-checker`
> **Full install** (all channels + all modes): add micromamba + abi-dumper stack

## Installation

### 1. Install abigail-tools (required)

```bash
sudo apt update && sudo apt install abigail-tools
abidiff --version  # should be 2.0+
```

### 2. Install abi-compliance-checker (for ABICC+headers mode)

```bash
sudo apt install abi-compliance-checker gcc
```

### 3. Install micromamba (for intel: and conda-forge: channels)

Only needed if you use `intel:` or `conda-forge:` package specs:

```bash
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
sudo mv bin/micromamba /usr/local/bin/
export MAMBA_ROOT_PREFIX=$HOME/.mamba
micromamba --version
```

### 4. Install abi-scanner

```bash
git clone https://github.com/napetrov/abi-scanner.git
cd abi-scanner
pip install -e .

abi-scanner --help  # verify installation
```

## Quick verification

```bash
# Should print help with subcommands: compare, list, compatible, validate, snapshot
abi-scanner --help

# Compare two oneDNN versions from Intel APT
abi-scanner compare \
  apt:intel-oneapi-dnnl=2025.2.0 \
  apt:intel-oneapi-dnnl=2025.3.0 \
  --library-name libdnnl.so \
  --apt-index-url https://apt.repos.intel.com/oneapi/dists/all/main/binary-amd64/Packages.gz
```

## macOS

```bash
brew install libabigail
# Note: abi-compliance-checker and abi-dumper are Linux-only
# On macOS only abidiff mode is available
```

## Troubleshooting

### `micromamba: command not found`
```bash
export PATH="$PATH:/usr/local/bin"
```

### `abidiff --version` shows < 2.0
Install from source: see [libabigail build instructions](https://sourceware.org/libabigail/manual/libabigail-overview.html#Build-and-install-the-abigail-tools).

### `abi-compliance-checker` not found
```bash
sudo apt install abi-compliance-checker
# or build from source: https://github.com/lvc/abi-compliance-checker
```

## See Also

- [README.md](../README.md) — overview and quick start
- [docs/local_compare.md](local_compare.md) — comparing local builds vs published releases
- [docs/tool_modes.md](tool_modes.md) — understanding analysis modes
- [docs/legacy/INSTALLATION_LEGACY.md](legacy/INSTALLATION_LEGACY.md) — old bash-script workflow (historical)
